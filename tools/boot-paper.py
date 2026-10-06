"""Real Paper boot: readiness ping, live-snapshot commands, snapshot restore and console stop.

Run after `make build GAME=paper` and `docker load -i build/paper/image.tar`:

    python3 tools/boot-paper.py [image]

Downloads the pinned bootstrap JAR (about 62 MiB) and lets the launcher fetch the
latest stable 26.2 build. Needs network access. No Minecraft account is used, so
this proves server readiness and snapshot consistency, not a client join.
"""
import hashlib
import json
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = json.loads((ROOT / 'images/paper/template.json').read_text())
ARTIFACT = TEMPLATE['runtime_artifact']
image = sys.argv[1] if len(sys.argv) > 1 else 'squab-paper:verify-amd64'
run_id = uuid.uuid4().hex[:12]
SEED = str(uuid.uuid4().int % 10**15)


def docker(*args, check=True, **kwargs):
    return subprocess.run(['docker', *args], capture_output=True, text=True, check=check, **kwargs)


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
    """Minecraft server list ping, the same check as readiness kind minecraft_status."""
    with socket.create_connection(('127.0.0.1', port), timeout=5) as sock:
        host = b'127.0.0.1'
        handshake = varint(0) + varint(772) + varint(len(host)) + host \
            + struct.pack('>H', port) + varint(1)
        sock.sendall(varint(len(handshake)) + handshake + varint(1) + varint(0))
        read_varint(sock)
        if read_varint(sock) != 0:
            raise RuntimeError('unexpected status packet')
        length = read_varint(sock)
        data = b''
        while len(data) < length:
            data += sock.recv(length - len(data))
        return json.loads(data)


class Server:
    def __init__(self, name, volume, runtime, port):
        self.name = name
        docker('run', '-d', '-i', '--name', name, '--read-only', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--pids-limit', '512',
               '--memory', '2g', '--memory-swap', '2g', '--cpus', '2',
               '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m,mode=1777',
               '--mount', f'type=volume,source={volume},target=/data',
               '--mount', f'type=bind,source={runtime},target=/squab-runtime,readonly',
               '-e', 'SQUAB_SYSTEM_LICENSE_ACCEPTED=true',
               '-p', f'127.0.0.1:{port}:25565', image)
        self.console = subprocess.Popen(['docker', 'attach', '--sig-proxy=false', name],
                                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, text=True)
        self.port = port

    def logs(self):
        return subprocess.run(['docker', 'logs', self.name], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, check=True).stdout

    def wait(self, text, after=0, timeout=300):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            logs = self.logs()
            if text in logs[after:]:
                return len(logs)
            state = json.loads(docker('inspect', '--format', '{{json .State}}', self.name).stdout)
            if not state['Running']:
                raise RuntimeError(f'Paper exited while waiting for {text!r}:\n{logs[-3000:]}')
            time.sleep(1)
        raise RuntimeError(f'timed out waiting for {text!r}:\n{self.logs()[-3000:]}')

    def send(self, line):
        self.console.stdin.write(line + '\n')
        self.console.stdin.flush()

    def ready(self):
        self.wait('Done (')
        deadline = time.monotonic() + 60
        while True:
            try:
                return status(self.port)
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)

    def stop(self):
        self.send('stop')
        docker('wait', self.name, timeout=90)
        state = json.loads(docker('inspect', '--format', '{{json .State}}', self.name).stdout)
        if state['ExitCode'] != 0 or state['OOMKilled']:
            raise RuntimeError(f'Paper did not stop cleanly: {state}')
        self.console.wait(timeout=10)
        docker('rm', self.name)


def prepare(volume):
    docker('volume', 'create', volume)
    # Wing writes trusted server.properties before start; mimic a minimal file.
    docker('run', '--rm', '--entrypoint', '/bin/sh', '--mount', f'type=volume,source={volume},target=/data',
           image, '-c', f'printf "motd=Squab boot check\\nlevel-seed={SEED}\\nonline-mode=false\\n" > /data/server.properties')


def main():
    names, volumes = [], []
    with tempfile.TemporaryDirectory() as temp:
        runtime = Path(temp) / 'runtime'
        runtime.mkdir()
        jar = runtime / f'{ARTIFACT["sha256"]}.jar'
        with urllib.request.urlopen(urllib.request.Request(
                ARTIFACT['download_url'], headers={'User-Agent': 'Squab-Paper/1 (https://github.com/squab-dev/squab-templates)'}),
                timeout=120) as response:
            jar.write_bytes(response.read())
        assert jar.stat().st_size == ARTIFACT['size_bytes']
        assert hashlib.sha256(jar.read_bytes()).hexdigest() == ARTIFACT['sha256']
        jar.chmod(0o444)
        runtime.chmod(0o755)
        try:
            source, restored = f'squab-paper-boot-{run_id}', f'squab-paper-restore-{run_id}'
            for volume in (source, restored):
                volumes.append(volume)
                prepare(volume)
            names.append(source)
            server = Server(source, source, runtime, 25600)
            ping = server.ready()
            print(f'ready: {ping["version"]["name"]}, protocol {ping["version"]["protocol"]}, '
                  f'{ping["players"]["max"]} slots, motd {ping["description"]!r}')
            props = docker('exec', source, 'cat', '/data/server.properties').stdout
            assert 'online-mode=true' in props, 'launcher must enforce online-mode=true'
            assert docker('exec', source, 'id', '-u').stdout.strip() == '65532'

            # The template's exact snapshot block, in order.
            mark = len(server.logs())
            for step in TEMPLATE['snapshot']['prepare']:
                server.send(step['command'])
                if 'await' in step:
                    mark = server.wait(step['await'], mark, step['timeout_seconds'])
            # Copy while autosave is off, excluding the template's exclude list.
            excludes = ' '.join(f'--exclude=./{path}' for path in TEMPLATE['snapshot']['exclude'])
            archive = Path(temp) / 'snapshot.tar'
            with archive.open('wb') as stream:
                subprocess.run(['docker', 'exec', source, '/bin/sh', '-c', f'cd /data && tar -cf - {excludes} .'],
                               stdout=stream, check=True)
            for step in TEMPLATE['snapshot']['resume']:
                server.send(step['command'])
            server.wait('Automatic saving is now enabled', mark, 30)
            print(f'snapshot: prepare/resume commands acknowledged; archive {archive.stat().st_size} bytes')
            server.stop()
            print('stop: console stop exited 0')

            # Restore the snapshot copy into a fresh volume and boot it.
            with archive.open('rb') as stream:
                subprocess.run(['docker', 'run', '--rm', '-i', '--entrypoint', '/bin/sh', '--mount',
                                f'type=volume,source={restored},target=/data', image, '-c',
                                # Only the restored level.dat can now supply the original seed.
                                "cd /data && tar -xf - && sed -i '/^level-seed=/d' server.properties"],
                               stdin=stream, check=True)
            names.append(restored)
            second = Server(restored, restored, runtime, 25601)
            second.ready()
            mark = len(second.logs())
            second.send('seed')
            second.wait(f'Seed: [{SEED}]', mark, 30)
            second.stop()
            print('restore: snapshot booted to readiness with the original world seed from level.dat')
            print('PASS: Paper boot, status ping, live-snapshot commands, snapshot restore and console stop')
        except Exception:
            for name in names:
                print(docker('logs', '--tail', '40', name, check=False).stdout)
            raise
        finally:
            for name in names:
                docker('rm', '-f', name, check=False)
            for volume in volumes:
                docker('volume', 'rm', volume, check=False)


if __name__ == '__main__':
    main()
