"""Keep reviewed Wolfi dependencies; bind the freshly built local launcher APK."""
import json
import sys
from pathlib import Path

base, resolved, output = map(Path, sys.argv[1:])
lock = json.loads(base.read_text())
fresh = json.loads(resolved.read_text())
if lock['config'] != fresh['config']:
    raise SystemExit('apko configuration changed: explicitly regenerate wolfi.lock.json')
local = [p for p in fresh['contents']['packages'] if p['name'] == 'squab-paper-launcher']
if len(local) != 1 or local[0]['architecture'] != 'x86_64':
    raise SystemExit('expected exactly one native launcher APK')
if any(not p['url'].startswith('https://packages.wolfi.dev/os/') for p in lock['contents']['packages']):
    raise SystemExit('unexpected remote package source')
lock['contents']['packages'].extend(local)
output.write_text(json.dumps(lock, indent=2) + '\n')
