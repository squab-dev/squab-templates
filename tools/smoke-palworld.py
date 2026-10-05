"""Real empty-world boot, authenticated readiness, graceful stop and recreation."""
import json
import subprocess
import time
import uuid

name = 'squab-palworld-smoke-' + uuid.uuid4().hex[:12]
volume = name + '-data'


def docker(*args, **kwargs):
    return subprocess.check_output(['docker', *args], text=True, **kwargs).strip()


def boot():
    docker('run', '-d', '-i', '--name', name, '--read-only', '--cap-drop', 'ALL',
           '--security-opt', 'no-new-privileges', '--pids-limit', '512',
           '--memory', '6g', '--memory-swap', '6g', '--cpus', '2',
           '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m,mode=1777',
           '--mount', f'type=volume,source={volume},target=/data',
           'squab-palworld:verify-amd64')
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        state = json.loads(docker('inspect', '--format', '{{json .State}}', name))
        if not state['Running']:
            raise RuntimeError('Palworld exited before readiness')
        if state.get('Health', {}).get('Status') == 'healthy':
            result = docker('exec', name, 'python3', '-c',
                'import runpy,json; m=runpy.run_path("/usr/local/bin/squab-palworld-launcher"); '
                'print(json.loads(m["api"]("GET","info"))["worldguid"])')
            return result
        time.sleep(2)
    raise RuntimeError('Palworld never became healthy')


def stop():
    # Exercise the exact stdin command used by Wing; Docker stop would test a different path.
    result = subprocess.run(['docker', 'attach', '--sig-proxy=false', name],
                            input='stop\n', text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Palworld console stop failed')
    state = json.loads(docker('inspect', '--format', '{{json .State}}', name))
    if state['Running'] or state['ExitCode'] != 0 or state['OOMKilled']:
        raise RuntimeError('Palworld did not stop cleanly')
    docker('rm', name)


try:
    first = boot()
    assert docker('exec', name, 'id', '-u') == '65532'
    stop()
    assert boot() == first, 'world identity changed after container recreation'
    stop()
    print('PASS: Palworld game API readiness, non-root execution, stdin stop and world persistence')
except Exception:
    subprocess.run(['docker', 'logs', '--tail', '35', name], check=False)
    raise
finally:
    subprocess.run(['docker', 'rm', '-f', name], capture_output=True, check=False)
    subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True, check=False)
