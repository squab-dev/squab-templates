"""Real CurseForge modpack boots on every Java line, against a local CurseForge double.

Run after building the image (it must be loaded as squab-curseforge:verify-amd64):

    python3 tools/boot-curseforge.py [--work DIR] [case ...]

No CurseForge API key is needed. The script starts an HTTPS double of
api.curseforge.com and edge.forgecdn.net on the Docker bridge gateway (port 443)
with a throw-away CA, and points the container at it with --add-host and a CA
bundle that adds the test CA. Everything else (Forge/NeoForge/Fabric maven,
Mojang) is the real internet. Each server pack is built from official files:
the loader installer or metadata, plus one real mod from Modrinth (verified by
SHA-512). Containers run like Wing runs them: UID 65532, read-only root, all
capabilities dropped, 64 MiB /tmp, 6 GiB memory=swap, 2 CPUs, 512 PIDs, the key
as /run/squab/secrets/CF_API_KEY (0400) with only CF_API_KEY_FILE in env.

For each case: boot to a Minecraft status ping, run the template's snapshot
commands and copy /data while saving is off, stop through the console, then
recreate the container and boot again (no second server pack download). The key
must not appear in any log, process argument, environment or /data file, and
only api.curseforge.com may receive it. Needs about 2 GiB of downloads.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tests'))
from curseforge_mock import MockCurseForge, make_zip, serve  # noqa: E402

IMAGE = 'squab-curseforge:verify-amd64'
TEMPLATE = json.loads((ROOT / 'images/curseforge/template.json').read_text())
MODRINTH = 'https://cdn.modrinth.com/data/'
CASES = {
    # Java 8: the most played legacy modded version; the pack ships the official installer.
    'forge-1.12.2': dict(java=8, minecraft='1.12.2', loader='forge', version='14.23.5.2860', hint='installer',
                         mod=('u6dRKJwZ/versions/BQ4twf0Y/jei_1.12.2-4.22.0.1035.jar', '25b9ac36ee24e587')),
    # Java 17: ServerPackCreator-style variables.txt.
    'forge-1.20.1': dict(java=17, minecraft='1.20.1', loader='forge', version='47.4.0', hint='variables',
                         mod=('u6dRKJwZ/versions/uyTkeINn/jei-1.20.1-forge-15.62.0.219.jar', '572918aad9d26b33')),
    # Java 21: no loader hint in the server pack, so the launcher reads the client manifest.
    'neoforge-1.21.1': dict(java=21, minecraft='1.21.1', loader='neoforge', version='21.1.256', hint='client',
                            mod=('u6dRKJwZ/versions/RI8WCow6/jei-1.21.1-neoforge-19.57.0.451.jar', 'fe1f0d431135e911')),
    # Java 25: the year-versioned Minecraft line, manifest.json inside the server pack.
    'fabric-26.2': dict(java=25, minecraft='26.2', loader='fabric', version='0.19.5', hint='manifest',
                        mod=('P7dR8mSH/versions/ewUK83HI/fabric-api-0.161.0%2B26.2.jar', '2502fa5ade78e9a1')),
}


def docker(*args, check=True, **kwargs):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check, **kwargs)


def fetch(url, cache):
    target = cache / hashlib.sha256(url.encode()).hexdigest()[:16]
    if not target.exists():
        request = urllib.request.Request(url, headers={'User-Agent': 'squab-templates boot check'})
        with urllib.request.urlopen(request, timeout=120) as response:
            target.write_bytes(response.read())
    return target.read_bytes()


def pack_files(case, cache):
    """Return (server_zip, client_zip) built from official files."""
    path, sha512_prefix = case['mod']
    mod = fetch(MODRINTH + path, cache)
    if not hashlib.sha512(mod).hexdigest().startswith(sha512_prefix):
        raise SystemExit('Modrinth file changed: ' + path)
    mod_name = path.rsplit('/', 1)[1].replace('%2B', '+')
    loader_id = f'{case["loader"]}-{case["version"]}'
    manifest = json.dumps({'minecraft': {'version': case['minecraft'], 'modLoaders': [
        {'id': loader_id, 'primary': True}]}, 'manifestType': 'minecraftModpack', 'manifestVersion': 1,
        'name': 'Squab boot ' + loader_id, 'version': '1.0.0', 'files': [], 'overrides': 'overrides'}).encode()
    server = {f'mods/{mod_name}': mod, 'config/squab-boot.txt': b'pack config\n',
              'server.properties': b'motd=Pack default motd\nonline-mode=false\nview-distance=6\n',
              'start.sh': b'#!/bin/sh\necho "never executed by Squab"\nexit 1\n'}
    if case['hint'] == 'installer':
        name = f'{case["minecraft"]}-{case["version"]}'
        server[f'forge-{name}-installer.jar'] = fetch(
            f'https://maven.minecraftforge.net/net/minecraftforge/forge/{name}/forge-{name}-installer.jar', cache)
    elif case['hint'] == 'variables':
        server['variables.txt'] = (f'MINECRAFT_VERSION={case["minecraft"]}\nMODLOADER=Forge\n'
                                   f'MODLOADER_VERSION={case["version"]}\nJAVA_ARGS="-Xmx4G"\n').encode()
    elif case['hint'] == 'manifest':
        server['manifest.json'] = manifest
    # Many authors zip one top-level folder.
    server = {f'ServerFiles-1.0.0/{name}': data for name, data in server.items()}
    return make_zip(server), make_zip({'manifest.json': manifest, 'overrides/config/client.txt': b'client\n'})


def varint(value):
    out = b''
    while True:
        byte = value & 0x7F
        value >>= 7
        out += bytes([byte | (0x80 if value else 0)])
        if not value:
            return out


def read_varint(sock):
    value = shift = 0
    while True:
        byte = sock.recv(1)[0]
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value


def status(port):
    """Minecraft server list ping, as readiness kind minecraft_status does."""
    with socket.create_connection(('127.0.0.1', port), timeout=5) as sock:
        handshake = varint(0) + varint(47) + varint(9) + b'127.0.0.1' + struct.pack('>H', port) + varint(1)
        sock.sendall(varint(len(handshake)) + handshake + varint(1) + varint(0))
        read_varint(sock)
        if read_varint(sock) != 0:
            raise OSError('unexpected status packet')
        length, data = read_varint(sock), b''
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                raise OSError('short status packet')
            data += chunk
        value = json.loads(data)
        # Forge answers "Server is still starting" with a bare text object; Wing's probe
        # accepts any JSON object, this check waits for a real status with a version.
        if not isinstance(value, dict) or 'version' not in value:
            raise OSError('server is still starting')
        return value


class Server:
    def __init__(self, name, volume, port, env, work, gateway):
        self.name, self.port = name, port
        arguments = ['run', '-d', '-i', '--name', name, '--user', '65532:65532', '--read-only',
                     '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--pids-limit', '512',
                     '--memory', '6g', '--memory-swap', '6g', '--cpus', '2',
                     '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,mode=1777',
                     '--mount', f'type=volume,source={volume},target=/data',
                     '--mount', f'type=bind,source={work / "secrets"},target=/run/squab/secrets,readonly',
                     '--mount', f'type=bind,source={work / "ca-bundle.crt"},target=/etc/ssl/certs/ca-certificates.crt,readonly',
                     '--add-host', f'api.curseforge.com:{gateway}', '--add-host', f'edge.forgecdn.net:{gateway}',
                     '-p', f'127.0.0.1:{port}:25565']
        for key, value in env.items():
            arguments += ['-e', f'{key}={value}']
        docker(*arguments, IMAGE)
        self.console = subprocess.Popen(['docker', 'attach', '--sig-proxy=false', name], stdin=subprocess.PIPE,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)

    def logs(self):
        return subprocess.run(['docker', 'logs', self.name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, check=True).stdout

    def running(self):
        return json.loads(docker('inspect', '--format', '{{json .State}}', self.name).stdout)['Running']

    def wait(self, texts, after=0, timeout=300):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            logs = self.logs()
            for text in texts:
                index = logs.find(text, after)
                if index >= 0:
                    end = logs.find('\n', index)
                    return len(logs), logs[logs.rfind('\n', 0, index) + 1:end].strip()
            if not self.running():
                raise RuntimeError(f'server exited while waiting for {texts}:\n{logs[-4000:]}')
            time.sleep(1)
        raise RuntimeError(f'timed out waiting for {texts}:\n{self.logs()[-4000:]}')

    def ready(self, timeout):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if not self.running():
                raise RuntimeError('server exited before readiness:\n' + self.logs()[-4000:])
            try:
                return status(self.port), time.monotonic() - start
            except (OSError, ValueError, IndexError):
                time.sleep(2)
        raise RuntimeError('no Minecraft status before the readiness deadline:\n' + self.logs()[-4000:])

    def send(self, line):
        self.console.stdin.write(line + '\n')
        self.console.stdin.flush()

    def stop(self, timeout):
        self.send(TEMPLATE['stop']['command'])
        docker('wait', self.name, timeout=timeout)
        state = json.loads(docker('inspect', '--format', '{{json .State}}', self.name).stdout)
        if state['ExitCode'] != 0 or state['OOMKilled']:
            raise RuntimeError(f'server did not stop cleanly: {state}')
        self.console.wait(timeout=10)


def certificates(work, gateway):
    """A throw-away CA and a server certificate for the two CurseForge hosts."""
    def openssl(*args):
        subprocess.run(['openssl', *args], check=True, capture_output=True)
    # Python 3.13+ verifies strictly: the CA needs key usage, the leaf an authority key ID.
    openssl('req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2', '-subj', '/CN=Squab boot check CA',
            '-addext', 'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
            '-addext', 'subjectKeyIdentifier=hash',
            '-keyout', str(work / 'ca.key'), '-out', str(work / 'ca.crt'))
    openssl('req', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=api.curseforge.com',
            '-keyout', str(work / 'server.key'), '-out', str(work / 'server.csr'))
    (work / 'san.ext').write_text('subjectAltName=DNS:api.curseforge.com,DNS:edge.forgecdn.net\n'
                                  'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n'
                                  'extendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\n'
                                  'authorityKeyIdentifier=keyid:always\n')
    openssl('x509', '-req', '-in', str(work / 'server.csr'), '-CA', str(work / 'ca.crt'), '-CAkey', str(work / 'ca.key'),
            '-CAcreateserial', '-days', '2', '-extfile', str(work / 'san.ext'), '-out', str(work / 'server.crt'))
    system = docker('run', '--rm', '--entrypoint', '/bin/cat', IMAGE, '/etc/ssl/certs/ca-certificates.crt').stdout
    (work / 'ca-bundle.crt').write_text(system + (work / 'ca.crt').read_text())
    (work / 'ca-bundle.crt').chmod(0o644)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(work / 'server.crt', work / 'server.key')
    return context


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--work', type=Path, default=ROOT / 'build/curseforge/boot')
    parser.add_argument('cases', nargs='*', default=list(CASES))
    args = parser.parse_args()
    work = args.work.resolve()
    if work.exists():
        shutil.rmtree(work / 'secrets', ignore_errors=True)
    (work / 'cache').mkdir(parents=True, exist_ok=True)
    gateway = docker('network', 'inspect', 'bridge', '-f', '{{(index .IPAM.Config 0).Gateway}}').stdout.strip()
    context = certificates(work, gateway)
    key = '$2a$10$' + secrets.token_urlsafe(40)
    (work / 'secrets').mkdir()
    secret = work / 'secrets/CF_API_KEY'
    secret.write_text(key)
    os.chown(secret, 65532, 65532)
    secret.chmod(0o400)
    os.chown(work / 'secrets', 65532, 65532)
    (work / 'secrets').chmod(0o500)

    mock = MockCurseForge(key)
    for number, name in enumerate(args.cases):
        case = CASES[name]
        server_zip, client_zip = pack_files(case, work / 'cache')
        mod_id = 900000 + number
        mock.add_mod(mod_id, 'squab-boot-' + name.replace('.', '-'), 'Squab boot ' + name)
        mock.add_version(mod_id, 7000000 + number * 1000, server_zip, f'{name} 1.0.0', '2026-10-01T00:00:00Z',
                         client_zip=client_zip, game_versions=(case['minecraft'], case['loader'].title()))
        case['mod_id'] = mod_id
    server = serve(mock, port=443, address=gateway, context=context)
    results, run = {}, uuid.uuid4().hex[:8]
    try:
        for number, name in enumerate(args.cases):
            case = CASES[name]
            volume = f'squab-cf-boot-{run}-{number}'
            docker('volume', 'create', volume)
            env = {'SQUAB_SYSTEM_LICENSE_ACCEPTED': 'true', 'CF_API_KEY_FILE': '/run/squab/secrets/CF_API_KEY',
                   'CF_MODPACK': f'squab-boot-{name.replace(".", "-")}', 'JAVA_VERSION': 'auto',
                   'WHITELIST_ENABLED': 'false', 'MAX_PLAYERS': '10', 'MOTD': f'Squab {name}'}
            evidence, logs = {}, []
            try:
                for boot in (1, 2):
                    container = f'squab-cf-boot-{run}-{number}-{boot}'
                    downloads = sum(r['host'] == 'edge.forgecdn.net' for r in mock.requests)
                    srv = Server(container, volume, 25700 + number, env, work, gateway)
                    try:
                        ping, seconds = srv.ready(TEMPLATE['readiness']['timeout_seconds'])
                        line = srv.wait(['Starting Minecraft'], 0, 10)[1]
                        assert f'on Java {case["java"]}' in line, line
                        boot_evidence = {'ready_seconds': round(seconds), 'launcher': line,
                                         'status_version': ping['version'].get('name'),
                                         'motd': json.dumps(ping.get('description'))[:80],
                                         'max_players': ping.get('players', {}).get('max'),
                                         'status_keys': sorted(ping)}
                        if boot == 1:
                            # docker exec inherits the container's configured environment, so
                            # inspect the server process (PID 1 after exec) itself.
                            procs = docker('exec', container, '/bin/sh', '-c',
                                           'for p in /proc/[0-9]*; do tr "\\0" " " < $p/cmdline; echo; done').stdout
                            environ = docker('exec', container, '/bin/sh', '-c', 'tr "\\0" "\\n" < /proc/1/environ').stdout
                            assert key not in procs and key not in environ and 'CF_API_KEY' not in environ
                            boot_evidence['server_env'] = sorted(line.split('=', 1)[0] for line in environ.split())
                            boot_evidence['uid'] = docker('exec', container, 'id', '-u').stdout.strip()
                            mods = srv.logs()
                            boot_evidence['mod_loaded'] = ('jei' in mods.lower() or 'fabric-api' in mods
                                                           or 'Fabric API' in mods)
                            mark = len(srv.logs())
                            saved = None
                            for step in TEMPLATE['snapshot']['prepare']:
                                srv.send(step['command'])
                                if 'await' in step:
                                    mark, saved = srv.wait([step['await']], mark, step['timeout_seconds'])
                            excludes = ' '.join(f'--exclude=./{p}' for p in TEMPLATE['snapshot']['exclude'])
                            copy = docker('exec', container, '/bin/sh', '-c',
                                          f'cd /data && tar -cf - {excludes} . | wc -c').stdout.strip()
                            for step in TEMPLATE['snapshot']['resume']:
                                srv.send(step['command'])
                            _, resumed = srv.wait(['Automatic saving is now enabled', 'Turned on world auto-saving',
                                                   'Saving is now enabled'], mark, 30)
                            boot_evidence['snapshot'] = {'saved_line': saved, 'resumed_line': resumed,
                                                         'copy_bytes': int(copy)}
                        else:
                            boot_evidence['server_pack_downloads'] = sum(
                                r['host'] == 'edge.forgecdn.net' for r in mock.requests) - downloads
                            assert boot_evidence['server_pack_downloads'] == 0
                        srv.stop(TEMPLATE['stop']['timeout_seconds'])
                        boot_evidence['stop'] = 'console stop, exit 0'
                    finally:
                        logs.append(srv.logs())
                        docker('rm', '-f', container, check=False)
                    evidence[f'boot{boot}'] = boot_evidence
                files = docker('run', '--rm', '--entrypoint', '/bin/sh', '--mount',
                               f'type=volume,source={volume},target=/data', IMAGE, '-c',
                               'if grep -rqF -e "$0" /data; then echo KEY-FOUND; fi; cat /data/server.properties', key).stdout
                assert key not in '\n'.join(logs) and 'KEY-FOUND' not in files
                assert 'online-mode=true' in files and 'max-players=10' in files and 'view-distance=6' in files
                evidence['key_in_logs_or_data'] = False
                results[name] = {'status': 'PASS', **evidence}
            except Exception as error:  # report and continue with the other Java lines
                results[name] = {'status': 'FAIL', 'error': str(error)[-3000:]}
                print('\n'.join(logs)[-6000:], file=sys.stderr)
            finally:
                docker('volume', 'rm', '-f', volume, check=False)
            print(json.dumps({name: results[name]}, indent=1), flush=True)
    finally:
        server.shutdown()
    keyed = {r['host'] for r in mock.requests if r['x-api-key'] is not None}
    results['_key_recipients'] = sorted(keyed)
    results['_requests'] = {host: sum(r['host'] == host for r in mock.requests)
                            for host in sorted({r['host'] for r in mock.requests})}
    assert keyed <= {'api.curseforge.com'}, keyed
    assert all(r['x-api-key'] in (None, key) for r in mock.requests)
    print(json.dumps(results, indent=1))
    shutil.rmtree(work / 'secrets', ignore_errors=True)
    return 0 if all(r.get('status') == 'PASS' for k, r in results.items() if not k.startswith('_')) else 1


if __name__ == '__main__':
    sys.exit(main())
