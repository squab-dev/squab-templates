"""A local CurseForge REST API and CDN double, shaped like https://docs.curseforge.com/rest-api/.

Used by the launcher unit tests (plain HTTP through a patched transport) and by
tools/boot-curseforge.py (HTTPS on port 443 with a test CA, reached through
Docker --add-host entries for api.curseforge.com and edge.forgecdn.net).
"""
import hashlib
import io
import json
import re
import threading
import urllib.parse
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API = 'api.curseforge.com'
CDN = 'edge.forgecdn.net'
MINECRAFT, MODPACKS = 432, 4471


def make_zip(entries, symlinks=()):
    """entries: {name: bytes}; symlinks: [(name, target)] stored with S_IFLNK mode."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
        for name, target in symlinks:
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o120777 << 16)
            archive.writestr(info, target)
    return buffer.getvalue()


class MockCurseForge:
    def __init__(self, key):
        self.key = key
        self.mods, self.files, self.blobs = {}, {}, {}
        self.requests = []
        self.rate_limit = 0          # number of 429 answers still to give
        self.lock = threading.Lock()

    # -- fixtures ---------------------------------------------------------------
    def add_mod(self, mod_id, slug, name, allow=True, class_id=MODPACKS):
        self.mods[mod_id] = {'id': mod_id, 'gameId': MINECRAFT, 'name': name, 'slug': slug,
                             'classId': class_id, 'allowModDistribution': allow, 'mainFileId': 0,
                             'isAvailable': True, 'status': 4, 'latestFiles': [], 'latestFilesIndexes': []}

    def add_file(self, mod_id, file_id, data, display, date, release_type=1, server_pack=None,
                 is_server_pack=False, parent=None, game_versions=('1.20.1', 'Forge'), cdn=True,
                 sha1=None, length=None):
        path = f'/files/{file_id // 1000}/{file_id % 1000}/{display.replace(" ", "_")}.zip'
        self.blobs[path] = data
        self.files[file_id] = {
            'id': file_id, 'gameId': MINECRAFT, 'modId': mod_id, 'isAvailable': True,
            'displayName': display, 'fileName': path.rsplit('/', 1)[1], 'releaseType': release_type,
            'fileStatus': 4, 'hashes': [{'value': sha1 or hashlib.sha1(data).hexdigest(), 'algo': 1},
                                        {'value': hashlib.md5(data).hexdigest(), 'algo': 2}],
            'fileDate': date, 'fileLength': len(data) if length is None else length, 'downloadCount': 1,
            'downloadUrl': f'https://{CDN}{path}' if cdn else None,
            'gameVersions': list(game_versions), 'sortableGameVersions': [], 'dependencies': [],
            'alternateFileId': 0, 'isServerPack': is_server_pack, 'serverPackFileId': server_pack,
            'parentProjectFileId': parent, 'fileFingerprint': 0, 'modules': []}
        return self.files[file_id]

    def add_version(self, mod_id, file_id, server_zip, display, date, client_zip=None, **options):
        """A client modpack file plus its server pack file (file_id + 100)."""
        server_id = file_id + 100
        self.add_file(mod_id, file_id, client_zip or make_zip({'manifest.json': b'{}'}), display, date,
                      server_pack=server_id, **options)
        self.add_file(mod_id, server_id, server_zip, display + ' Server', date, is_server_pack=True,
                      parent=file_id, game_versions=options.get('game_versions', ('1.20.1', 'Forge')),
                      cdn=options.get('cdn', True))

    # -- protocol ---------------------------------------------------------------
    def handle(self, host, target, headers):
        with self.lock:
            self.requests.append({'host': host, 'path': target,
                                  'x-api-key': headers.get('x-api-key')})
        host = (host or '').split(':')[0]
        if host == API:
            return self.api(target, headers)
        if host.endswith('forgecdn.net'):
            if headers.get('x-api-key') is not None:
                return 400, {}, b'credential sent to the CDN'
            data = self.blobs.get(urllib.parse.urlsplit(target).path)
            return (200, {'Content-Type': 'application/zip'}, data) if data is not None else (404, {}, b'')
        return 404, {}, b''

    def api(self, target, headers):
        if headers.get('x-api-key') != self.key:
            return 403, {}, b''
        with self.lock:
            if self.rate_limit:
                self.rate_limit -= 1
                return 429, {'Retry-After': '0'}, b''
        url = urllib.parse.urlsplit(target)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path == '/v1/mods/search':
            found = [m for m in self.mods.values()
                     if str(m['gameId']) == query.get('gameId') and str(m['classId']) == query.get('classId', str(m['classId']))
                     and m['slug'] == query.get('slug', m['slug'])]
            return self.ok({'data': found, 'pagination': {'index': 0, 'pageSize': 50,
                                                         'resultCount': len(found), 'totalCount': len(found)}})
        match = re.fullmatch(r'/v1/mods/(\d+)(?:/files(?:/(\d+)(/download-url)?)?)?', url.path)
        if not match or int(match.group(1)) not in self.mods:
            return 404, {}, b''
        mod = self.mods[int(match.group(1))]
        if match.group(2):
            file = self.files.get(int(match.group(2)))
            if not file or file['modId'] != mod['id']:
                return 404, {}, b''
            if match.group(3):
                if not mod['allowModDistribution'] or not file['downloadUrl']:
                    return 403, {}, b''
                return self.ok({'data': file['downloadUrl']})
            return self.ok({'data': file})
        if url.path.endswith('/files'):
            files = sorted((f for f in self.files.values() if f['modId'] == mod['id']), key=lambda f: -f['id'])
            index, size = int(query.get('index', 0)), min(int(query.get('pageSize', 50)), 50)
            page = files[index:index + size]
            return self.ok({'data': page, 'pagination': {'index': index, 'pageSize': size,
                                                        'resultCount': len(page), 'totalCount': len(files)}})
        return self.ok({'data': mod})

    @staticmethod
    def ok(value):
        return 200, {'Content-Type': 'application/json'}, json.dumps(value).encode()


def serve(mock, port=0, address='127.0.0.1', context=None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            status, headers, body = mock.handle(self.headers.get('Host'), self.path,
                                                {k.lower(): v for k, v in self.headers.items()})
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((address, port), Handler)
    if context is not None:
        server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
