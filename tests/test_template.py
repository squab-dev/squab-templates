import json
import subprocess
import tempfile
import unittest
import jsonschema
from pathlib import Path

class TemplateTests(unittest.TestCase):
    def test_manifest_requires_real_digest_and_changes_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'manifest.json'
            command = ['python3', 'tools/render-manifest.py', '--output', str(output), '--image']
            for image in ['ghcr.io/squab-dev/squab-paper:latest', 'ghcr.io/squab-dev/squab-paper@sha256:' + '0' * 64]:
                self.assertNotEqual(subprocess.run(command + [image], capture_output=True).returncode, 0)
            image = 'ghcr.io/squab-dev/squab-paper@sha256:' + '0123456789abcdef' * 4
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
