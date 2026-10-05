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
        self.assertEqual(json.loads((root/'health-manifest.json').read_text())['ServerVersion'], '>=' + version)
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

    def test_newer_release_accepted_but_old_or_prerelease_rejected(self):
        (self.root/'Server').mkdir()
        for p in setup.installed_files(self.root):
            p.write_bytes(b'game')
        receipt = self.root/'receipt'
        for version in ['0.6.7 (release)', '0.6.9 (pre-release)']:
            with patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'HytaleServer v' + version, '')):
                with self.assertRaises(setup.SetupError):
                    setup.record_install(self.root, receipt, {'version': '0.6.8'})
            self.assertFalse(receipt.exists())
        with patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'HytaleServer v0.6.9 (release)', '')):
            setup.record_install(self.root, receipt, {'version': '0.6.8'})
        setup.verify_install(self.root, receipt, {'version': '0.6.8'})

    def stage(self):
        staged = self.root/'updater/staging'
        (staged/'Server').mkdir(parents=True)
        for p in setup.installed_files(staged):
            p.write_bytes(b'new-' + p.name.encode())
        with patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'HytaleServer v0.6.9 (release)', '')):
            setup.record_install(staged, staged/'squab-install.json', {'version': '0.6.8'})
        return staged

    def test_update_requires_completed_download_and_preserves_world_auth_and_config(self):
        receipt = self.install()
        staged = self.stage()
        complete = (staged/'squab-install.json').read_text()
        (staged/'squab-install.json').unlink()
        pin = {'version': '0.6.8'}
        self.assertFalse(setup.apply_staged_update(self.root, receipt, pin))
        self.assertEqual((self.root/'Assets.zip').read_bytes(), b'Assets.zip')
        (staged/'squab-install.json').write_text(complete)
        private = [self.root/'Server/universe/world', self.root/'Server/auth.enc', self.root/'Server/config.json']
        for p in private:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'keep-me')
        self.assertTrue(setup.apply_staged_update(self.root, receipt, pin))
        setup.verify_install(self.root, receipt, pin)
        self.assertEqual(json.loads(receipt.read_text())['version'], '0.6.9')
        self.assertTrue(all(p.read_bytes() == b'keep-me' for p in private))
        self.assertFalse(setup.apply_staged_update(self.root, receipt, pin))

    def test_interrupted_update_resumes_after_each_rename_and_cleanup(self):
        pin = {'version': '0.6.8'}
        # Exercise interruption before/after moving both files and during cleanup.
        for stop in range(1, 10):
            with self.subTest(stop=stop), tempfile.TemporaryDirectory() as temporary:
                original_root = self.root
                self.root = Path(temporary)
                receipt = self.install()
                self.stage()
                calls = 0
                replace, unlink = Path.replace, Path.unlink
                def interrupt(method):
                    def wrapped(path, *args, **kwargs):
                        nonlocal calls
                        result = method(path, *args, **kwargs)
                        calls += 1
                        if calls == stop:
                            raise OSError('simulated process interruption')
                        return result
                    return wrapped
                with patch.object(Path, 'replace', interrupt(replace)), patch.object(Path, 'unlink', interrupt(unlink)):
                    try:
                        setup.apply_staged_update(self.root, receipt, pin)
                    except OSError:
                        pass
                setup.apply_staged_update(self.root, receipt, pin)
                setup.verify_install(self.root, receipt, pin)
                self.assertEqual(json.loads(receipt.read_text())['version'], '0.6.9')
                self.root = original_root

    def test_startup_update_config_retains_game_settings(self):
        path = self.root/'config.json'
        path.write_text(json.dumps({'ServerName': 'Keep', 'Update': {'Enabled': True, 'AutoApplyMode': 'WhenEmpty'}}))
        setup.prepare_update_config(self.root)
        config = json.loads(path.read_text())
        self.assertEqual(config['ServerName'], 'Keep')
        self.assertEqual(config['Update']['AutoApplyMode'], 'Disabled')
        self.assertFalse(config['Update']['Enabled'])

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

    def test_stop_during_download_or_integrity_check_prevents_next_java_launch(self):
        setup.terminate(None, None)
        with patch.object(setup.subprocess, 'Popen') as spawn:
            self.assertEqual(setup.run_java([], self.root), 0)
            spawn.assert_not_called()

    def test_health_refuses_missing_unhealthy_or_invalid_response(self):
        with patch.object(setup.urllib.request, 'urlopen', side_effect=OSError):
            self.assertFalse(setup.healthcheck())
        for code, body, expected in [(200, b'{"ready":true}', True), (503, b'{"ready":true}', False),
                                     (200, b'{"ready":false}', False), (200, b'not-json', False)]:
            response = io.BytesIO(body)
            response.status = code
            with patch.object(setup.urllib.request, 'urlopen', return_value=response):
                self.assertEqual(setup.healthcheck(), expected)
