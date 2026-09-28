import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / 'images/hytale/squab-hytale-launcher'

class HytaleLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        for name in ['HytaleServer.jar', 'Assets.zip']:
            (self.runtime / name).write_bytes(name.encode())
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        java = self.bin / 'java'
        java.write_text('#!/bin/sh\nprintf "%s\\n" "$HYTALE_DISABLE_UPDATES" "$@"\n')
        java.chmod(0o755)
        self.env = {'PATH': f'{self.bin}:' + os.environ['PATH'],
                    'HYTALE_RUNTIME_DIR': str(self.runtime),
                    'HYTALE_SERVER_SHA256': hashlib.sha256(b'HytaleServer.jar').hexdigest(),
                    'HYTALE_ASSETS_SHA256': hashlib.sha256(b'Assets.zip').hexdigest()}

    def run_launcher(self, extra=None, args=()):
        return subprocess.run(['sh', str(LAUNCHER), *args], cwd=self.root,
                              env={**self.env, **(extra or {})}, capture_output=True, text=True)

    def test_verified_files_launch_authenticated_without_updates(self):
        result = self.run_launcher({'HYTALE_PORT': '5521', 'HYTALE_HEAP_PERCENT': '70', 'HYTALE_DISABLE_UPDATES': 'false'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['true', '-XX:MaxRAMPercentage=70', '-jar',
            str(self.runtime/'HytaleServer.jar'), '--assets', str(self.runtime/'Assets.zip'),
            '--bind', '0.0.0.0:5521', '--auth-mode', 'authenticated', '--disable-sentry'])

    def test_missing_changed_or_symlinked_files_do_not_start_java(self):
        for name in ['HytaleServer.jar', 'Assets.zip']:
            p = self.runtime/name
            p.unlink()
            self.assertEqual(self.run_launcher().returncode, 65)
            p.write_bytes(b'tampered')
            self.assertEqual(self.run_launcher().returncode, 65)
            p.unlink()
            target=self.root/name
            target.write_bytes(name.encode())
            p.symlink_to(target)
            self.assertEqual(self.run_launcher().returncode, 65)
            p.unlink()
            p.write_bytes(name.encode())

    def test_invalid_settings_fail_without_exposing_values(self):
        for extra in [{'HYTALE_PORT':'0'}, {'HYTALE_PORT':'65536'}, {'HYTALE_PORT':'5520; touch hacked'},
                      {'HYTALE_HEAP_PERCENT':'100'}, {'HYTALE_SERVER_SHA256':''},
                      {'HYTALE_ASSETS_SHA256':'f'*63}, {'JDK_JAVA_OPTIONS':'sensitive-test-value'},
                      {'HYTALE_RUNTIME_DIR':'relative'}]:
            result=self.run_launcher(extra)
            self.assertEqual(result.returncode, 64, result.stderr)
            self.assertNotIn('sensitive-test-value',result.stderr)
            self.assertEqual(result.stdout,'')
        self.assertEqual(self.run_launcher(args=['--auth-mode','offline']).returncode,64)

    def test_shared_lock_merger_accepts_hytale_without_refreshing_remote_packages(self):
        base=json.loads((ROOT/'images/hytale/wolfi.lock.json').read_text())
        fresh=json.loads(json.dumps(base))
        fresh['contents']['packages'][0]['version']='future'
        local={'name':'squab-hytale-launcher','architecture':'x86_64','url':'local.apk'}
        fresh['contents']['packages'].append(local)
        source=self.root/'fresh.json';out=self.root/'merged.json'
        source.write_text(json.dumps(fresh))
        subprocess.run(['python3','tools/merge-lock.py','images/hytale/wolfi.lock.json',str(source),str(out),'squab-hytale-launcher'],check=True)
        self.assertEqual(json.loads(out.read_text())['contents']['packages'],base['contents']['packages']+[local])
