"""CurseForge launcher against a local double of the CurseForge REST API and CDN."""
import contextlib
import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from curseforge_mock import MockCurseForge, make_zip, serve  # noqa: E402

loader = importlib.machinery.SourceFileLoader('curseforge', str(ROOT / 'images/curseforge/squab-curseforge-launcher'))
spec = importlib.util.spec_from_loader(loader.name, loader)
cf = importlib.util.module_from_spec(spec)
loader.exec_module(cf)

KEY = '$2a$10$squabTestOnlyKeyValue.NotAReal/CurseForgeKey0123456789'
FABRIC_MANIFEST = json.dumps({'minecraft': {'version': '1.21.1', 'modLoaders': [
    {'id': 'fabric-0.16.14', 'primary': True}]}, 'manifestType': 'minecraftModpack'}).encode()


def fabric_pack(marker=b'v1', extra=None):
    """A server pack that already contains its launcher, so no installer runs in unit tests."""
    entries = {'manifest.json': FABRIC_MANIFEST, 'fabric-server-launch.jar': b'launch', 'server.jar': b'vanilla',
               'mods/example.jar': b'mod ' + marker, 'config/example.toml': b'value=' + marker,
               'server.properties': b'motd=Pack default\nmax-players=8\nonline-mode=false\n',
               'start.sh': b'#!/bin/sh\nrm -rf /\n', 'eula.txt': b'eula=false\n'}
    entries.update(extra or {})
    return make_zip(entries)


class Launcher(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        secret = self.root / 'secrets/CF_API_KEY'
        secret.parent.mkdir()
        secret.write_text(KEY)
        self.mock = MockCurseForge(KEY)
        self.mock.add_mod(1000, 'squab-test-pack', 'Squab Test Pack')
        self.mock.add_version(1000, 2001, fabric_pack(b'v1'), 'Pack 1.0.0', '2026-01-01T00:00:00Z',
                              game_versions=('1.21.1', 'Fabric'))
        self.mock.add_version(1000, 2002, fabric_pack(b'v2'), 'Pack 1.1.0', '2026-02-01T00:00:00Z',
                              game_versions=('1.21.1', 'Fabric'))
        # A newer beta and a newer release without a server pack are not chosen by default.
        self.mock.add_version(1000, 2003, fabric_pack(b'beta'), 'Pack 1.2.0-beta', '2026-03-01T00:00:00Z',
                              release_type=2, game_versions=('1.21.1', 'Fabric'))
        self.mock.add_file(1000, 2004, make_zip({'manifest.json': FABRIC_MANIFEST}), 'Pack 1.3.0 client only',
                           '2026-04-01T00:00:00Z')
        server = serve(self.mock)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        class Routed(http.client.HTTPConnection):
            """Plain HTTP to the local double, but with the real virtual host name."""
            def __init__(self, host):
                super().__init__('127.0.0.1', port, timeout=10)
                self.virtual_host = host

            def putrequest(self, method, url, **kwargs):
                super().putrequest(method, url, skip_host=True, **kwargs)
                self.putheader('Host', self.virtual_host)

        for name, value in {'DATA': self.data, 'STATE': self.data / '.squab-curseforge',
                            'SECRET_PATH': str(secret), 'connect': Routed}.items():
            patcher = patch.object(cf, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(cf.time, 'sleep', lambda seconds: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.env = {'SQUAB_SYSTEM_LICENSE_ACCEPTED': 'true', 'CF_API_KEY_FILE': str(secret),
                    'CF_MODPACK': 'squab-test-pack', 'JAVA_VERSION': 'auto', 'WHITELIST_ENABLED': 'false'}
        self.output = io.StringIO()

    def run_launcher(self, **env):
        """Returns (exit code, java argv). Output is captured to prove the key never appears."""
        environment = {k: v for k, v in {**self.env, **env}.items() if v is not None}
        with contextlib.redirect_stderr(self.output), contextlib.redirect_stdout(self.output):
            try:
                command, lock = cf.prepare(environment)
                lock.close()
                return 0, command
            except cf.Fail as failure:
                print('[Squab] CurseForge: ' + str(failure), file=sys.stderr)
                return failure.code, None

    def assert_key_private(self):
        self.assertNotIn(KEY, self.output.getvalue())
        self.assertNotIn(KEY[8:30], self.output.getvalue())
        for path in self.data.rglob('*'):
            if path.is_file():
                self.assertNotIn(KEY.encode(), path.read_bytes(), path)
        for request in self.mock.requests:
            if request['x-api-key'] is not None:
                self.assertEqual(request['host'], 'api.curseforge.com', request)
                self.assertEqual(request['x-api-key'], KEY)
            else:
                self.assertNotEqual(request['host'], 'api.curseforge.com', request)

    def tearDown(self):
        self.assert_key_private()

    def test_latest_release_by_slug_installs_and_configures(self):
        code, command = self.run_launcher(MAX_PLAYERS='12', MOTD='Hello §a world')
        self.assertEqual(code, 0, self.output.getvalue())
        self.assertEqual(command[0], '/usr/lib/jvm/java-21-openjdk/bin/java')
        self.assertEqual(command[-3:], ['-jar', 'fabric-server-launch.jar', 'nogui'])
        self.assertIn('-XX:MaxRAMPercentage=75.0', command)
        self.assertEqual((self.data / 'mods/example.jar').read_bytes(), b'mod v2')
        self.assertEqual((self.data / 'eula.txt').read_text(), 'eula=true\n')
        properties = (self.data / 'server.properties').read_text()
        for line in ['online-mode=true', 'max-players=12', 'server-port=25565', 'white-list=false',
                     'motd=Hello \\u00a7a world']:
            self.assertIn(line, properties.splitlines())
        self.assertNotIn('online-mode=false', properties)
        self.assertIn('Pack 1.1.0', self.output.getvalue())
        self.assertIn('has no server pack', self.output.getvalue())
        # A restart with no newer version re-uses the installation without downloading.
        downloads = len([r for r in self.mock.requests if r['host'] == 'edge.forgecdn.net'])
        self.assertEqual(self.run_launcher()[0], 0)
        self.assertEqual(downloads, len([r for r in self.mock.requests if r['host'] == 'edge.forgecdn.net']))

    def test_project_id_url_and_explicit_file_id(self):
        code, _ = self.run_launcher(CF_MODPACK='1000', CF_FILE_ID='2001')
        self.assertEqual(code, 0, self.output.getvalue())
        self.assertEqual((self.data / 'mods/example.jar').read_bytes(), b'mod v1')
        self.assertFalse(any('/search' in r['path'] for r in self.mock.requests))
        # Pinned and installed: a restart needs no API call at all.
        before = len(self.mock.requests)
        self.assertEqual(self.run_launcher(CF_MODPACK='1000', CF_FILE_ID='2001')[0], 0)
        self.assertEqual(before, len(self.mock.requests))
        self.assertEqual(cf.parse_modpack('https://www.curseforge.com/minecraft/modpacks/squab-test-pack/files/2001'),
                         ('slug', 'squab-test-pack'))
        for bad in ['', '../x', 'a b', 'https://evil.example/minecraft/modpacks/x', '0', '99999999999']:
            with self.assertRaises(cf.Fail):
                cf.parse_modpack(bad)

    def test_update_preserves_world_and_user_files(self):
        self.assertEqual(self.run_launcher(CF_FILE_ID='2001')[0], 0)
        (self.data / 'world/region').mkdir(parents=True)
        (self.data / 'world/level.dat').write_bytes(b'my world')
        (self.data / 'mods/user-added.jar').write_bytes(b'mine')
        (self.data / 'config/example.toml').write_bytes(b'edited by owner')
        (self.data / 'ops.json').write_text('[]')
        props = (self.data / 'server.properties').read_text().replace('motd=Pack default', 'motd=Mine')
        (self.data / 'server.properties').write_text(props)
        # Version 2 drops a mod and ships a world that must not overwrite the existing one.
        self.mock.add_version(1000, 2005, fabric_pack(b'v5', {'world/level.dat': b'pack world',
                                                              'mods/new.jar': b'new'}),
                              'Pack 2.0.0', '2026-05-01T00:00:00Z', game_versions=('1.21.1', 'Fabric'))
        old_mod_v1 = self.data / 'mods/example.jar'
        self.assertEqual(self.run_launcher(CF_FILE_ID='2005')[0], 0, self.output.getvalue())
        self.assertEqual((self.data / 'world/level.dat').read_bytes(), b'my world')
        self.assertEqual((self.data / 'mods/user-added.jar').read_bytes(), b'mine')
        self.assertEqual(old_mod_v1.read_bytes(), b'mod v5')
        self.assertTrue((self.data / 'mods/new.jar').exists())
        self.assertEqual((self.data / 'config/example.toml').read_bytes(), b'value=v5')
        backups = list((self.data / '.squab-curseforge/replaced').rglob('example.toml'))
        self.assertEqual([b.read_bytes() for b in backups], [b'edited by owner'])
        self.assertIn('motd=Mine', (self.data / 'server.properties').read_text())
        # Removing a pack file the owner had not modified deletes it.
        self.mock.add_version(1000, 2006, make_zip({'manifest.json': FABRIC_MANIFEST,
                                                    'fabric-server-launch.jar': b'launch', 'server.jar': b'vanilla'}),
                              'Pack 3.0.0', '2026-06-01T00:00:00Z', game_versions=('1.21.1', 'Fabric'))
        self.assertEqual(self.run_launcher(CF_FILE_ID='2006')[0], 0)
        self.assertFalse((self.data / 'mods/new.jar').exists())
        self.assertTrue((self.data / 'mods/user-added.jar').exists())

    def test_changed_modpack_is_refused(self):
        self.assertEqual(self.run_launcher()[0], 0)
        self.mock.add_mod(1001, 'other-pack', 'Other')
        self.mock.add_version(1001, 3001, fabric_pack(), 'Other 1', '2026-01-01T00:00:00Z')
        code, _ = self.run_launcher(CF_MODPACK='other-pack')
        self.assertEqual(code, 64)
        self.assertIn('different modpack', self.output.getvalue())

    def test_loader_detection_from_client_manifest(self):
        forge = json.dumps({'minecraft': {'version': '1.20.1', 'modLoaders': [{'id': 'forge-47.4.0', 'primary': True}]}})
        self.mock.add_version(1000, 2010, make_zip({'Pack/mods/a.jar': b'a'}), 'Pack no hints', '2026-07-01T00:00:00Z',
                              client_zip=make_zip({'manifest.json': forge.encode(), 'overrides/x': b'x'}))
        installed = []
        with patch.object(cf, 'install_loader', lambda *args: installed.append(args[1:4]) or ['-jar', 'x.jar']):
            code, command = self.run_launcher(CF_FILE_ID='2010')
        self.assertEqual(code, 0, self.output.getvalue())
        self.assertEqual(installed, [('forge', '1.20.1', '47.4.0')])
        self.assertTrue((self.data / 'mods/a.jar').exists(), 'single top-level folder is stripped')
        self.assertEqual(command[0], '/usr/lib/jvm/java-17-openjdk/bin/java')

    def test_loader_hints_in_server_pack(self):
        root = self.root / 'hints'
        root.mkdir()
        (root / 'forge-1.12.2-14.23.5.2860-installer.jar').write_bytes(b'')
        self.assertEqual(cf.detect_loader(root), ('1.12.2', 'forge', '14.23.5.2860'))
        (root / 'forge-1.12.2-14.23.5.2860-installer.jar').unlink()
        (root / 'variables.txt').write_text('MINECRAFT_VERSION=1.20.1\nMODLOADER=NeoForge\nMODLOADER_VERSION="47.1.106"\n')
        self.assertEqual(cf.detect_loader(root), ('1.20.1', 'neoforge', '47.1.106'))
        (root / 'variables.txt').unlink()
        (root / 'neoforge-21.1.209-installer.jar').write_bytes(b'')
        self.assertEqual(cf.detect_loader(root), ('1.21.1', 'neoforge', '21.1.209'))
        self.assertEqual(cf.neoforge_minecraft('26.1.0.12'), '26.1')

    def test_java_selection(self):
        cases = {'1.7.10': 8, '1.12.2': 8, '1.16.5': 8, '1.17.1': 17, '1.18.2': 17, '1.20.1': 17, '1.20.4': 17,
                 '1.20.5': 21, '1.20.6': 21, '1.21': 21, '1.21.1': 21, '1.21.11': 21, '26.1': 25, '26.2': 25,
                 '26.3.1': 25}
        for version, java in cases.items():
            self.assertEqual(cf.java_for(version), java, version)
        with self.assertRaises(cf.Fail):
            cf.java_for('b1.7.3')
        code, command = self.run_launcher(JAVA_VERSION='25')
        self.assertEqual(command[0], '/usr/lib/jvm/java-25-openjdk/bin/java')
        self.assertIn('overrides the automatic choice', self.output.getvalue())

    def test_missing_or_misdelivered_key(self):
        self.assertEqual(self.run_launcher(CF_API_KEY_FILE=None)[0], 64)
        self.assertIn('CF_API_KEY is not set', self.output.getvalue())
        self.assertEqual(self.run_launcher(CF_API_KEY='x')[0], 64)
        self.assertEqual(self.run_launcher(CF_API_KEY_FILE='/etc/passwd')[0], 64)
        Path(cf.SECRET_PATH).write_text('bad\nkey')
        self.assertEqual(self.run_launcher()[0], 64)
        self.assertIn('invalid format', self.output.getvalue())
        Path(cf.SECRET_PATH).write_text(KEY)
        self.assertEqual(self.run_launcher(SQUAB_SYSTEM_LICENSE_ACCEPTED=None)[0], 64)
        self.assertEqual(self.run_launcher(JAVA_TOOL_OPTIONS='-Xmx1g')[0], 64)
        self.assertEqual(self.run_launcher(SQUAB_SYSTEM_OTHER='1')[0], 64)

    def test_invalid_key_is_rejected_with_403(self):
        self.mock.key = 'a-different-key'
        code, _ = self.run_launcher()
        self.assertEqual(code, 64)
        self.assertIn('rejected the API key (HTTP 403)', self.output.getvalue())

    def test_unknown_project(self):
        self.assertEqual(self.run_launcher(CF_MODPACK='424242')[0], 64)
        self.assertIn('was not found', self.output.getvalue())
        self.assertEqual(self.run_launcher(CF_MODPACK='no-such-pack')[0], 64)
        self.mock.add_mod(1002, 'a-mod', 'Not a pack', class_id=6)
        self.assertEqual(self.run_launcher(CF_MODPACK='1002')[0], 64)
        self.assertIn('not a Minecraft modpack', self.output.getvalue())

    def test_no_server_pack(self):
        self.assertEqual(self.run_launcher(CF_FILE_ID='2004')[0], 64)
        self.assertIn('has no server pack', self.output.getvalue())
        self.mock.add_mod(1003, 'clients-only', 'Clients only')
        self.mock.add_file(1003, 4001, make_zip({'manifest.json': b'{}'}), 'Only client', '2026-01-01T00:00:00Z')
        self.assertEqual(self.run_launcher(CF_MODPACK='clients-only')[0], 64)
        self.assertIn('No version of this modpack has a server pack', self.output.getvalue())

    def test_distribution_disallowed(self):
        self.mock.add_mod(1004, 'private-pack', 'Private', allow=False)
        self.mock.add_version(1004, 5001, fabric_pack(), 'P1', '2026-01-01T00:00:00Z')
        self.assertEqual(self.run_launcher(CF_MODPACK='private-pack')[0], 64)
        self.assertIn('allowModDistribution=false', self.output.getvalue())
        # Project allows it, but the file has no public download location.
        self.mock.add_mod(1005, 'hidden-file', 'Hidden')
        self.mock.add_version(1005, 6001, fabric_pack(), 'H1', '2026-01-01T00:00:00Z', cdn=False)
        self.assertEqual(self.run_launcher(CF_MODPACK='hidden-file')[0], 64)
        self.assertIn('does not allow third-party downloads', self.output.getvalue())

    def test_rate_limit_retries_then_fails(self):
        self.mock.rate_limit = 2
        self.assertEqual(self.run_launcher()[0], 0, self.output.getvalue())
        self.assertIn('HTTP 429; retrying', self.output.getvalue())
        self.mock.rate_limit = 100
        code, _ = self.run_launcher()
        # Installed already: a transient failure starts the installed version.
        self.assertEqual(code, 0)
        self.assertIn('starting the installed version', self.output.getvalue())
        shutil_state = self.data / '.squab-curseforge/state.json'
        shutil_state.unlink()
        self.assertEqual(self.run_launcher()[0], 65)
        self.assertIn('rate limit reached (HTTP 429)', self.output.getvalue())

    def test_hash_mismatch(self):
        self.mock.add_version(1000, 2020, fabric_pack(b'x'), 'Bad hash', '2026-08-01T00:00:00Z')
        self.mock.files[2120]['hashes'][0]['value'] = '0' * 40
        self.assertEqual(self.run_launcher(CF_FILE_ID='2020')[0], 65)
        self.assertIn('checksum verification failed', self.output.getvalue())
        self.assertFalse((self.data / 'mods').exists())
        self.mock.files[2120]['hashes'] = [{'value': 'a' * 32, 'algo': 2}]
        self.assertEqual(self.run_launcher(CF_FILE_ID='2020')[0], 65)
        self.assertIn('no SHA-1', self.output.getvalue())

    def test_zip_slip_and_links_are_rejected(self):
        for number, archive in enumerate([
                make_zip({'mods/ok.jar': b'1', '../escape.txt': b'x'}),
                make_zip({'mods/ok.jar': b'1', '/etc/evil': b'x'}),
                make_zip({'mods/ok.jar': b'1', 'mods\\..\\..\\evil': b'x'}),
                make_zip({'mods/ok.jar': b'1'}, symlinks=[('config', '/etc')])]):
            file_id = 2030 + number
            self.mock.add_version(1000, file_id, archive, f'Slip {number}', '2026-08-01T00:00:00Z')
            self.assertEqual(self.run_launcher(CF_FILE_ID=str(file_id))[0], 65)
            self.assertFalse((self.root / 'escape.txt').exists())
            self.assertFalse((self.data / 'mods/ok.jar').exists())
        self.assertIn('unsafe path', self.output.getvalue())
        self.assertIn('link or special file', self.output.getvalue())

    def test_oversized_archives(self):
        self.mock.add_version(1000, 2040, fabric_pack(), 'Huge', '2026-08-01T00:00:00Z')
        self.mock.files[2140]['fileLength'] = 3 * 1024**3
        self.assertEqual(self.run_launcher(CF_FILE_ID='2040')[0], 65)
        self.assertIn('larger than Squab allows (2 GiB)', self.output.getvalue())
        bomb = make_zip({'manifest.json': FABRIC_MANIFEST, 'bomb.bin': b'\0' * (8 * 1024**2)})
        self.mock.add_version(1000, 2041, bomb, 'Bomb', '2026-08-01T00:00:00Z')
        self.assertEqual(self.run_launcher(CF_FILE_ID='2041')[0], 65)
        self.assertIn('compression ratio', self.output.getvalue())
        with patch.object(cf, 'MAX_UNPACKED', 1024):
            self.mock.add_version(1000, 2042, fabric_pack(extra={'big.bin': os.urandom(4096)}), 'Big',
                                  '2026-08-01T00:00:00Z')
            self.assertEqual(self.run_launcher(CF_FILE_ID='2042')[0], 65)
        self.assertIn('larger than Squab allows (8 GiB)', self.output.getvalue())
        # A download longer than the declared size is cut off and discarded.
        self.mock.add_version(1000, 2043, fabric_pack(), 'Lies', '2026-08-01T00:00:00Z')
        self.mock.files[2143]['fileLength'] -= 10
        self.assertEqual(self.run_launcher(CF_FILE_ID='2043')[0], 65)
        self.assertIn('exceeded its expected size', self.output.getvalue())


class Transport(unittest.TestCase):
    def test_key_header_only_for_the_api_host(self):
        with self.assertRaises(AssertionError):
            cf.request('https://edge.forgecdn.net/x', {'x-api-key': 'k'})
        with self.assertRaises(cf.Fail):
            cf.request('http://api.curseforge.com/v1/mods/1', {'x-api-key': 'k'})
        self.assertNotIn('secret-value', repr(cf.CurseForge('secret-value')))

    def test_download_locations_must_be_the_cdn(self):
        api = cf.CurseForge('k')
        for url in ['https://evil.example/x.zip', 'http://edge.forgecdn.net/x.zip', 'https://edge.forgecdn.net.evil/x']:
            with self.assertRaises(cf.Fail):
                api.download_url(1, {'id': 1, 'downloadUrl': url})


class Template(unittest.TestCase):
    def test_manifest_follows_sensitive_configuration_rules(self):
        manifest = json.loads((ROOT / 'images/curseforge/template.json').read_text())
        jsonschema.Draft202012Validator(json.loads((ROOT / 'api/vendor/template.schema.json').read_text())).validate(
            dict(manifest, image='ghcr.io/squab-dev/squab-templates/curseforge:0.0.1', revision_id=manifest['id']))
        fields = manifest['configuration_schema']['properties']
        key = fields['CF_API_KEY']
        self.assertEqual(key, {'type': 'string', 'minLength': 1, 'maxLength': 4096, 'sensitive': True})
        self.assertIn('CF_API_KEY', manifest['configuration_schema']['required'])
        self.assertNotIn('CF_API_KEY_FILE', fields)
        self.assertTrue(fields['CF_MODPACK']['create_only'])
        self.assertEqual(manifest['readiness']['kind'], 'minecraft_status')
        self.assertEqual(manifest['license']['document_url'], 'https://www.minecraft.net/en-us/eula')
        self.assertGreaterEqual(manifest['minimum_limits']['memory_mib'], 6144)

    def test_launcher_and_image_agree(self):
        launcher = (ROOT / 'images/curseforge/squab-curseforge-launcher').read_text()
        apko = (ROOT / 'images/curseforge/apko.yaml').read_text()
        for java in (8, 17, 21, 25):
            self.assertIn(f'openjdk-{java}-jre=', apko)
            self.assertIn(cf.JAVA[java], launcher)
        lock = json.loads((ROOT / 'images/curseforge/wolfi.lock.json').read_text())
        self.assertTrue(all(p['url'].startswith('https://packages.wolfi.dev/os/') for p in lock['contents']['packages']))
        compile(launcher, 'squab-curseforge-launcher', 'exec')


if __name__ == '__main__':
    unittest.main()
