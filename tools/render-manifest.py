"""Render a new immutable catalog revision from an actual registry image digest."""
import argparse
import json
import re
import uuid
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--image', required=True)
p.add_argument('--output', type=Path, required=True)
args = p.parse_args()
if not re.fullmatch(r'ghcr\.io/squab-dev/squab-templates/paper@sha256:[0-9a-f]{64}', args.image):
    p.error('expected a digest-pinned ghcr.io/squab-dev/squab-templates/paper image')
if len(set(args.image.rsplit(':', 1)[1])) == 1:
    p.error('placeholder digests are not publishable')
manifest = json.loads(Path('images/paper/template.json').read_text())
manifest['image'] = args.image
# Rebuilding an image must never overwrite an existing immutable revision.
manifest['revision_id'] = str(uuid.uuid5(uuid.UUID(manifest['id']), args.image))
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(manifest, indent=2) + '\n')
