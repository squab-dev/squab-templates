"""Real JVM bootstrap smoke without an account or authenticated game download."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

engine = os.environ.get('CONTAINER_ENGINE', 'docker')
image = sys.argv[1]
name = 'squab-hytale-smoke-' + uuid.uuid4().hex[:12]


def docker(*args, check=True):
    return subprocess.run([engine, *args], capture_output=True, text=True, check=check)


assert docker('run', '--rm', '--entrypoint', '/bin/id', image, '-u').stdout.strip() == '65532'
docker('run', '--rm', '--entrypoint', '/bin/sh', image, '-ec',
       'test -x /usr/local/bin/squab-hytale-setup; test -f /opt/squab-hytale/plugins/readiness.jar; '
       'test ! -e /opt/squab-hytale/HytaleServer.jar; test ! -e /opt/squab-hytale/Assets.zip; '
       'test "$HOME" = /data; java -version')
with tempfile.TemporaryDirectory(prefix='squab-hytale-smoke-') as directory:
    root = Path(directory)
    os.chmod(root, 0o777)
    try:
        docker('run', '-di', '--name', name, '--read-only', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=64m,mode=1777',
               '--memory=2g', '--memory-swap=2g', '--cpus=2', '--pids-limit=256',
               '--mount', f'type=bind,src={root},dst=/data', image)
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            logs = docker('logs', name).stdout
            state = json.loads(docker('inspect', name).stdout)[0]['State']
            if not state['Running']:
                raise RuntimeError('Hytale exited before the owner sign-in prompt: ' + logs[-4000:])
            if 'Enter code:' in logs and 'Waiting for authorization' in logs:
                break
            time.sleep(1)
        else:
            raise RuntimeError('Hytale did not request owner sign-in within 150 seconds: ' + logs[-4000:])
        assert docker('exec', name, '/usr/local/bin/squab-hytale-setup', '--healthcheck', check=False).returncode == 1
        assert state['Health']['Status'] != 'healthy'
        assert not (root/'game/Assets.zip').exists()
        pin = json.loads(Path('images/hytale/bootstrap.json').read_text())
        with (root/'game/HytaleServer.jar').open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == pin['sha256']
        docker('stop', '-t', '30', name)
        state = json.loads(docker('inspect', name).stdout)[0]['State']
        assert state['ExitCode'] == 0, state['ExitCode']
        print('Hytale: non-root, read-only, pinned bootstrap, owner login, unauthenticated health and graceful stop passed.')
        print('An authorized game download, world boot and client connection require the server owner; this smoke does not claim them.')
    finally:
        docker('rm', '-f', name, check=False)
