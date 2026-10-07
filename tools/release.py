"""Plan incremental image builds and generate the catalog for a verified release."""
import argparse
import hashlib
import json
import re
import subprocess
import uuid
from pathlib import Path

import jsonschema

STATE = 'release-state.json'
BUILD_TOOLS = ('tools/build.sh', 'tools/install-tools.sh', 'tools/merge-lock.py',
               '.github/workflows/image.yml', 'Makefile', 'requirements-dev.txt')
RELEASE_TOOLS = ('tools/release.py', 'tools/render-manifest.py', 'tools/publish-release.py',
                 '.github/workflows/release.yml', 'api/vendor/template.schema.json')
# Artwork in this repository is served from raw GitHub. Template sources name the
# mutable `main` path; released manifests pin it to their own release tag.
ARTWORK = re.compile(r'https://raw\.githubusercontent\.com/squab-dev/squab-templates/'
                     r'([A-Za-z0-9._-]+)/(artwork/[a-z0-9][a-z0-9._-]*\.webp)')
RELEASE_TAG = re.compile(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def fingerprint(root, paths):
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        content = (root / path).read_bytes()
        digest.update(path.encode() + b'\0' + str(len(content)).encode() + b'\0' + content)
    return digest.hexdigest()


def inputs(root):
    result = {}
    for config in sorted(root.glob('images/*/apko.yaml')):
        game = config.parent.name
        if not re.fullmatch('[a-z][a-z0-9-]*', game):
            raise ValueError('invalid image directory name')
        # Documentation, local Compose examples and catalog metadata do not enter the image.
        tracked = subprocess.check_output(
            ['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others',
             '--exclude-standard', '--', f'images/{game}'], text=True).split('\0')
        paths = [p for p in tracked if p and (root / p).is_file()
                 and Path(p).suffix != '.md'
                 and Path(p).name not in ('template.json', 'compose.yaml')]
        template = config.parent / 'template.json'
        smoke = 'tools/smoke.sh' if game == 'paper' else f'tools/smoke-{game}.sh'
        result[game] = {
            'build': fingerprint(root, [*paths, *BUILD_TOOLS, smoke]),
            'template': fingerprint(root, [str(template.relative_to(root))])
            if template.exists() else None,
        }
    if not result:
        raise ValueError('no images configured')
    return result


def plan(root):
    current = inputs(root)
    state = read_json(root / STATE) if (root / STATE).exists() else {}
    previous = state.get('images', {})
    # Compare with the last release, never just the previous push. Failed/skipped
    # workflows therefore leave their changes pending for the next successful run.
    builds = [game for game, hashes in current.items()
              if previous.get(game, {}).get('build') != hashes['build']]
    release_hash = fingerprint(root, RELEASE_TOOLS)
    changed = (current != {game: {'build': data['build'], 'template': data['template']}
                           for game, data in previous.items()}
               or state.get('release_tools') != release_hash)
    return {'build': builds, 'release': changed, 'inputs': current,
            'release_tools': release_hash}


def validate_image(game, image):
    if not re.fullmatch(r'[a-z][a-z0-9-]*', game):
        raise ValueError('invalid game name')
    if not re.fullmatch(r'ghcr\.io/squab-dev/squab-templates/' + re.escape(game)
                        + r'(?:@sha256:[0-9a-f]{64}|:(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))', image):
        raise ValueError('expected a release-tagged or historical digest image in the game package')
    if '@sha256:' in image and len(set(image.rsplit(':', 1)[1])) == 1:
        raise ValueError('placeholder digests are not publishable')


def artwork_ref(manifest):
    """Git ref of repository-hosted artwork, or None for other or absent artwork."""
    match = ARTWORK.fullmatch(manifest.get('artwork_url', ''))
    return match.group(1) if match else None


def render_manifest(root, game, image, ref=None):
    """Render a manifest; `ref` pins repository artwork to that release tag."""
    validate_image(game, image)
    manifest = read_json(root / 'images' / game / 'template.json')
    manifest['image'] = image
    match = ARTWORK.fullmatch(manifest.get('artwork_url', ''))
    if ref is not None and match:
        if ref != 'main' and not RELEASE_TAG.fullmatch(ref):
            raise ValueError('artwork must be pinned to a release tag')
        manifest['artwork_url'] = ('https://raw.githubusercontent.com/squab-dev/squab-templates/'
                                   f'{ref}/{match.group(2)}')
    manifest.pop('revision_id', None)
    # Metadata changes must also produce a new revision when the image is reused.
    canonical = json.dumps(manifest, sort_keys=True, separators=(',', ':'))
    manifest['revision_id'] = str(uuid.uuid5(uuid.UUID(manifest['id']), canonical))
    jsonschema.Draft202012Validator(read_json(root / 'api/vendor/template.schema.json')).validate(manifest)
    if manifest['test_only']:
        raise ValueError('test-only templates cannot enter the public catalog')
    return manifest


def next_version(tags):
    versions = [tuple(map(int, tag[1:].split('.'))) for tag in tags
                if re.fullmatch(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', tag)]
    major, minor, patch = max(versions, default=(0, 0, 0))
    return f'v{major}.{minor}.{patch + 1}'


def recovery_tag(root, source):
    """A pushed release commit survives a failed GitHub Release API call."""
    for tag in git(root, 'tag', '--list', 'v*', '--sort=-version:refname').splitlines():
        if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
            continue
        result = subprocess.run(['git', '-C', str(root), 'show', f'{tag}:{STATE}'],
                                text=True, capture_output=True)
        if result.returncode == 0 and json.loads(result.stdout).get('source') == source:
            return tag
    return ''


def assemble(root, planned, artifacts, version, source, output):
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', version):
        raise ValueError('invalid release version')
    if not re.fullmatch(r'[0-9a-f]{40}', source):
        raise ValueError('invalid source commit')
    if planned != plan(root):
        raise ValueError('release inputs changed after planning')
    previous = read_json(root / STATE).get('images', {}) if (root / STATE).exists() else {}
    state = {'version': version, 'source': source,
             'release_tools': planned['release_tools'], 'images': {}}
    manifests = []
    for game, hashes in planned['inputs'].items():
        old = previous.get(game, {})
        if game in planned['build']:
            verified = (artifacts / f'image-{game}' / 'image-reference.txt').read_text().strip()
        else:
            verified = old.get('verified_image', old['image'])
        validate_image(game, verified)
        if '@sha256:' not in verified:
            raise ValueError('verified registry digest is required as build evidence')
        # Unchanged images keep their original release tag. Legacy digest entries
        # gain a tag without rebuilding or altering historical manifests.
        image = (f'ghcr.io/squab-dev/squab-templates/{game}:{version[1:]}'
                 if game in planned['build'] or '@sha256:' in old.get('image', '')
                 else old['image'])
        if old.get('image') == image and old.get('verified_image', verified) != verified:
            raise ValueError('refusing to overwrite an immutable image release')
        entry = dict(hashes, image=image, verified_image=verified, manifest=None)
        if hashes['template'] is not None:
            old_path = old.get('manifest')
            # An unchanged template keeps its published manifest, including the
            # artwork ref it was released with (historical ones use `main`).
            published = read_json(root / old_path) if old_path else None
            ref = artwork_ref(published) if published else None
            if published and (ref is None or ref == 'main' or RELEASE_TAG.fullmatch(ref)) \
                    and render_manifest(root, game, image, ref) == published:
                path = old_path
            else:
                # The release tag contains this commit's artwork, so the immutable
                # manifest never follows later artwork changes on main.
                manifest = render_manifest(root, game, image, version)
                artwork = ARTWORK.fullmatch(manifest.get('artwork_url', ''))
                if artwork and not (root / artwork.group(2)).is_file():
                    raise ValueError(f'missing artwork {artwork.group(2)}')
                path = f'releases/{game}/{version[1:]}.json'
                if (root / path).exists():
                    raise ValueError('refusing to overwrite an immutable release')
                write_json(output / path, manifest)
            entry['manifest'] = path
            manifests.append(path)
        state['images'][game] = entry
    history = {str(path.relative_to(root)) for path in (root / 'releases').glob('*/*.json')}
    manifests = sorted(history | set(manifests), key=lambda path: (tuple(int(part) for part in Path(path).stem.split('.')), path))
    if not 1 <= len(manifests) <= 100:
        raise ValueError('catalog must contain between 1 and 100 templates')
    write_json(output / 'catalog.json', {'schema_version': 1, 'manifests': manifests})
    write_json(output / STATE, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    root = Path('.')
    planned = plan(root)
    source = git(root, 'rev-parse', 'HEAD')
    recovered = recovery_tag(root, source)
    write_json(args.output, planned)
    if args.github_output:
        with args.github_output.open('a') as output:
            output.write('matrix=' + json.dumps({'game': [] if recovered else planned['build']}) + '\n')
            output.write(f'build={str(bool(planned["build"]) and not recovered).lower()}\n')
            output.write(f'release={str(planned["release"] or bool(recovered)).lower()}\n')
            output.write(f'recover={recovered}\n')
    print(json.dumps(dict(planned, recover=recovered), indent=2))


if __name__ == '__main__':
    main()
