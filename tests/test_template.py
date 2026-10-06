import json
import subprocess
import tempfile
import unittest
import jsonschema
from pathlib import Path

class TemplateTests(unittest.TestCase):
    def test_launcher_and_catalog_pin_the_same_runtime_artifact(self):
        artifact = json.loads(Path('images/paper/template.json').read_text())['runtime_artifact']
        launcher = Path('images/paper/squab-paper-launcher').read_text().splitlines()
        self.assertIn('artifact=/squab-runtime/' + artifact['sha256'] + '.jar', launcher)
        self.assertIn('expected_sha256=' + artifact['sha256'], launcher)
        self.assertIn('expected_size=' + str(artifact['size_bytes']), launcher)

    def test_manifest_requires_real_digest_and_changes_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'manifest.json'
            command = ['python3', 'tools/render-manifest.py', '--output', str(output), '--image']
            for image in ['ghcr.io/squab-dev/squab-templates/paper:latest', 'ghcr.io/squab-dev/squab-templates/paper@sha256:' + '0' * 64]:
                self.assertNotEqual(subprocess.run(command + [image], capture_output=True).returncode, 0)
            image = 'ghcr.io/squab-dev/squab-templates/paper@sha256:' + '0123456789abcdef' * 4
            subprocess.run(command + [image], check=True)
            first = json.loads(output.read_text())
            jsonschema.Draft202012Validator(json.loads(Path('api/vendor/template.schema.json').read_text())).validate(first)
            self.assertEqual(first['image'], image)
            self.assertTrue(first['license']['acceptance_required'])
            self.assertEqual(first['architectures'], ['amd64'])
            subprocess.run(command + [image], check=True)
            self.assertEqual(first, json.loads(output.read_text()))
            subprocess.run(command + [image.replace('0123', '1234')], check=True)
            self.assertNotEqual(first['revision_id'], json.loads(output.read_text())['revision_id'])

    def test_live_snapshot_is_declared_only_with_verified_console_commands(self):
        schema = jsonschema.Draft202012Validator(json.loads(Path('api/vendor/template.schema.json').read_text()))
        paper = json.loads(Path('images/paper/template.json').read_text())
        self.assertIn('live_snapshot', paper['capabilities'])
        self.assertEqual(paper['snapshot'], {
            'prepare': [{'command': 'save-off'},
                        {'command': 'save-all flush', 'await': 'Saved the game', 'timeout_seconds': 60}],
            'resume': [{'command': 'save-on'}],
            'exclude': ['logs', 'crash-reports', 'cache'],
        })
        without_block = {k: v for k, v in paper.items() if k != 'snapshot'}
        self.assertFalse(schema.is_valid(without_block))
        without_capability = dict(paper, capabilities=[c for c in paper['capabilities'] if c != 'live_snapshot'])
        self.assertFalse(schema.is_valid(without_capability))
        # Other games have no verified console save sequence and keep stopped backups only.
        for game in ['palworld', 'hytale']:
            manifest = json.loads(Path(f'images/{game}/template.json').read_text())
            self.assertNotIn('live_snapshot', manifest['capabilities'])
            self.assertNotIn('snapshot', manifest)

    def test_launcher_rejects_untrusted_input_before_java(self):
        import os
        launcher = ['sh', 'images/paper/squab-paper-launcher']
        for extra in [{}, {'SQUAB_SYSTEM_LICENSE_ACCEPTED': 'false'},
                      {'SQUAB_SYSTEM_LICENSE_ACCEPTED': 'true', 'JAVA_TOOL_OPTIONS': '-Xmx8g'},
                      {'SQUAB_SYSTEM_LICENSE_ACCEPTED': 'true', 'SQUAB_SYSTEM_EVIL': 'true'}]:
            result = subprocess.run(launcher, env={'PATH': os.environ['PATH'], **extra}, capture_output=True)
            self.assertEqual(result.returncode, 64, result.stderr)

    def test_lock_preserves_remote_checksums(self):
        base = json.loads(Path('images/paper/wolfi.lock.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            fresh = json.loads(json.dumps(base))
            fresh['contents']['packages'][0]['version'] = 'future'
            local = {'name': 'squab-paper-launcher', 'architecture': 'x86_64', 'url': 'local.apk'}
            fresh['contents']['packages'].append(local)
            resolved, output = Path(tmp)/'fresh.json', Path(tmp)/'merged.json'
            resolved.write_text(json.dumps(fresh))
            subprocess.run(['python3', 'tools/merge-lock.py', 'images/paper/wolfi.lock.json', str(resolved), str(output)], check=True)
            self.assertEqual(json.loads(output.read_text())['contents']['packages'], base['contents']['packages'] + [local])
            fresh['config']['checksum'] = 'changed'
            resolved.write_text(json.dumps(fresh))
            self.assertNotEqual(subprocess.run(['python3', 'tools/merge-lock.py', 'images/paper/wolfi.lock.json', str(resolved), str(output)], capture_output=True).returncode, 0)
