import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('hytale_setup', str(ROOT/'images/hytale/squab-hytale-setup'))
spec = importlib.util.spec_from_loader(loader.name, loader)
setup = importlib.util.module_from_spec(spec)
loader.exec_module(setup)


class HytaleSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        setup.child = None
        setup.stopping = False

    def test_account_and_jvm_injection_rejected_without_disclosure(self):
        for key in ['HYTALE_SERVER_SESSION_TOKEN', 'HYTALE_SERVER_IDENTITY_TOKEN',
                    'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS', 'JVM_ARGS']:
            with patch.dict(os.environ, {key: 'private-value'}, clear=True):
                with self.assertRaises(setup.SetupError) as failure:
                    setup.settings()
                self.assertNotIn('private-value', str(failure.exception))

    def test_configuration_boundaries(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(setup.settings(), (5520, 75, []))
        for values in [{'HYTALE_PORT': '5521'}, {'HYTALE_PORT': '65536'},
                       {'HYTALE_PORT': '1023'}, {'HYTALE_HEAP_PERCENT': '86'},
                       {'HYTALE_OWNER_UUID': '../profile'}]:
            with patch.dict(os.environ, values, clear=True), self.assertRaises(setup.SetupError):
                setup.settings()

    def test_profile_selection_file_is_validated_and_confined(self):
        game = self.root/'game'
        game.mkdir()
        profile = game/'profile.json'
        selected = '55c1e2d3-82ca-48c2-bf9d-9f88e9805994'
        with patch.dict(os.environ, {}, clear=True), patch.object(setup.Path, 'cwd', return_value=self.root):
            profile.write_text(json.dumps({'uuid': selected}))
            self.assertEqual(setup.settings()[2], ['--owner-uuid', selected])
            for value in [[], {'uuid': 42}, {'uuid': 'invalid'}, {'uuid': selected, 'token': 'private'}]:
                profile.write_text(json.dumps(value))
                with self.assertRaises(setup.SetupError):
                    setup.settings()
            profile.unlink()
            profile.symlink_to(self.root/'absent')
            with self.assertRaises(setup.SetupError):
                setup.settings()

    def test_bootstrap_plugin_and_catalog_select_same_version(self):
        root = ROOT/'images/hytale'
        version = json.loads((root/'bootstrap.json').read_text())['version']
        self.assertEqual(json.loads((root/'health-manifest.json').read_text())['ServerVersion'], '=' + version)
        self.assertEqual(json.loads((root/'template.json').read_text())['game_version'], version)

    def test_bootstrap_size_hash_and_redirect_are_checked(self):
        data = b'public-test-bootstrap'
        pin = {'url': 'https://example.invalid/server.jar', 'size': len(data),
               'sha256': hashlib.sha256(data).hexdigest()}
        for content, succeeds in [(data, True), (data+b'x', False), (b'wrong', False)]:
            response = io.BytesIO(content)
            response.status = 200
            target = self.root/'bootstrap.jar'
            target.unlink(missing_ok=True)
            with patch.object(setup.urllib.request.OpenerDirector, 'open', return_value=response):
                if succeeds:
                    setup.fetch_bootstrap(target, pin)
                    self.assertEqual(target.read_bytes(), data)
                else:
                    with self.assertRaises(setup.SetupError):
                        setup.fetch_bootstrap(target, pin)
                    self.assertFalse(target.exists())
            self.assertEqual(list(self.root.glob('.download-*')), [])
        self.assertIsNone(setup.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.invalid'))

    def test_cached_bootstrap_never_follows_symlinks_or_overwrites_bad_files(self):
        target = self.root/'bootstrap.jar'
        target.symlink_to(self.root/'missing')
        pin = {'size': 4, 'sha256': hashlib.sha256(b'good').hexdigest()}
        with self.assertRaises(setup.SetupError):
            setup.fetch_bootstrap(target, pin)
        target.unlink()
        target.write_bytes(b'bad')
        with self.assertRaises(setup.SetupError):
            setup.fetch_bootstrap(target, pin)
        self.assertEqual(target.read_bytes(), b'bad')

    def install(self):
        (self.root/'Server').mkdir()
        for p in setup.installed_files(self.root):
            p.write_bytes(p.name.encode())
        receipt = self.root/'squab-install.json'
        with patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'HytaleServer v0.6.8 (release)\n', '')):
            setup.record_install(self.root, receipt, {'version': '0.6.8'})
        return receipt

    def test_install_receipt_detects_replacement_and_malformed_records(self):
        receipt = self.install()
        pin = {'version': '0.6.8'}
        setup.verify_install(self.root, receipt, pin)
        good = receipt.read_text()
        for record in [[], {'version': '0.6.8', 'files': None},
                       {'version': '0.6.8', 'files': [None, None]}]:
            receipt.write_text(json.dumps(record))
            with self.assertRaises(setup.SetupError):
                setup.verify_install(self.root, receipt, pin)
        receipt.write_text(good)
        (self.root/'Assets.zip').write_bytes(b'changed')
        with self.assertRaises(setup.SetupError):
            setup.verify_install(self.root, receipt, pin)

    def test_different_downloaded_game_version_is_not_accepted(self):
        (self.root/'Server').mkdir()
        for p in setup.installed_files(self.root):
            p.write_bytes(b'game')
        with patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'HytaleServer v99.0.0 (release)\n', '')):
            with self.assertRaises(setup.SetupError):
                setup.record_install(self.root, self.root/'receipt', {'version': '0.6.8'})
        self.assertFalse((self.root/'receipt').exists())

    def test_installer_waits_for_auth_and_requests_download_once(self):
        class Child:
            def __init__(self):
                self.stdin = io.StringIO()
                self.stdout = io.StringIO('Waiting for authorization\n[2026/10/05 18:00:00 INFO] [AbstractCommand] Authentication successful! Use auth status\nAuthentication successful! Duplicate\n')
            def poll(self): return None
            def wait(self): return 0
        child = Child()
        with patch.object(setup.subprocess, 'Popen', return_value=child) as spawn, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(setup.run_java(['--bootstrap'], self.root, bootstrap=True), 0)
        self.assertEqual(child.stdin.getvalue(), 'update setup\n')
        self.assertEqual(spawn.call_args.kwargs['env']['HYTALE_DISABLE_UPDATES'], 'false')

    def test_health_refuses_missing_unhealthy_or_invalid_response(self):
        with patch.object(setup.urllib.request, 'urlopen', side_effect=OSError):
            self.assertFalse(setup.healthcheck())
        for code, body, expected in [(200, b'{"ready":true}', True), (503, b'{"ready":true}', False),
                                     (200, b'{"ready":false}', False), (200, b'not-json', False)]:
            response = io.BytesIO(body)
            response.status = code
            with patch.object(setup.urllib.request, 'urlopen', return_value=response):
                self.assertEqual(setup.healthcheck(), expected)
