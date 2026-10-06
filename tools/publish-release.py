"""Commit/tag generated catalog data and publish recoverable GitHub releases."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from release import STATE, assemble, git, next_version, read_json, recovery_tag, validate_image


def run(*args):
    subprocess.run(args, check=True)


def package_catalog(root, destination):
    """Include relative manifest paths so an extracted catalog is self-contained."""
    destination.mkdir(parents=True, exist_ok=True)
    paths = ['catalog.json', STATE, *read_json(root / 'catalog.json')['manifests']]
    for name in ('catalog.json', STATE):
        shutil.copyfile(root / name, destination / name)
    with tarfile.open(destination / 'catalog.tar.gz', 'w:gz') as archive:
        for path in paths:
            archive.add(root / path, arcname=path, recursive=False)
    return [destination / name for name in ('catalog.json', STATE, 'catalog.tar.gz')]


def publish_github_release(root, tag):
    assets = package_catalog(root, root / 'build/release-assets')
    state = read_json(root / STATE)
    notes = root / 'build/release-notes.md'
    notes.write_text(
        f'Generated from source commit `{state["source"]}`.\n\n'
        f'Immutable catalog: https://raw.githubusercontent.com/squab-dev/squab-templates/{tag}/catalog.json\n\n'
        'The catalog archive contains the index and its manifests with their relative paths. '
        'Image references and build fingerprints are recorded in `release-state.json`. '
        'SBOMs and verification logs are retained in the source workflow run.\n\n'
        + '\n'.join(f'- {game}: `{data["image"]}`' for game, data in state['images'].items()) + '\n'
    )
    existing = subprocess.run(['gh', 'release', 'view', tag, '--json', 'isDraft'],
                              capture_output=True, text=True)
    if existing.returncode == 0:
        if not json.loads(existing.stdout)['isDraft']:
            print(f'{tag} is already published; nothing to change.')
            return
    else:
        run('gh', 'release', 'create', tag, '--verify-tag', '--draft',
            '--title', tag, '--notes-file', str(notes))
    # A failed upload leaves a draft. Re-running the source workflow repairs it
    # from the immutable tag without rebuilding or replacing released images.
    run('gh', 'release', 'upload', tag, *map(str, assets), '--clobber')
    # Avoid moving Latest backwards when an older failed release is retried.
    versions = [value for value in git(root, 'tag', '--list', 'v*').splitlines()
                if re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', value)]
    latest = tag == max(versions, key=lambda value: tuple(map(int, value[1:].split('.'))))
    run('gh', 'release', 'edit', tag, '--draft=false',
        '--latest' if latest else '--latest=false')


class ImageTagConflict(ValueError):
    pass


def registry_digest(image):
    result = subprocess.run(['docker', 'buildx', 'imagetools', 'inspect', image,
                             '--format', '{{json .Manifest}}'],
                            capture_output=True, text=True)
    if result.returncode:
        if any(code in result.stderr.lower() for code in ('not found', 'manifest unknown', '404')):
            return None
        raise RuntimeError(f'cannot inspect {image}: {result.stderr.strip()}')
    digest = json.loads(result.stdout)['digest']
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('registry returned an invalid image digest')
    return digest


def publish_image_tags(state):
    pending = []
    for game, entry in state['images'].items():
        image, verified = entry['image'], entry['verified_image']
        validate_image(game, image)
        validate_image(game, verified)
        expected = verified.split('@', 1)[1]
        existing = registry_digest(image)
        if existing is not None and existing != expected:
            raise ImageTagConflict(f'refusing to overwrite released image {image}')
        if existing is None:
            pending.append((image, verified, expected))
    # Preflight every tag before publishing any. Retag the already verified
    # registry manifest without rebuilding or changing its format/content.
    for image, verified, expected in pending:
        run('docker', 'buildx', 'imagetools', 'create', '--prefer-index=false',
            '--tag', image, verified)
        if registry_digest(image) != expected:
            raise ValueError(f'published image tag does not match build evidence: {image}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_REF') != 'refs/heads/main' or os.environ.get('GITHUB_EVENT_NAME') not in ('push', 'workflow_dispatch'):
        parser.error('publication is restricted to main push/manual workflows')
    root = Path('.')
    source = os.environ['GITHUB_SHA']
    run('git', 'fetch', 'origin', 'main', '--tags')
    tag = recovery_tag(root, source)
    if tag:
        run('git', 'checkout', '--detach', tag)
        publish_github_release(root, tag)
        return
    if git(root, 'rev-parse', 'origin/main') != source:
        print('Main has advanced; the next workflow will include these unreleased changes.')
        return
    if git(root, 'rev-parse', 'HEAD') != source:
        raise ValueError('checkout does not match the source workflow commit')
    planned = read_json(args.plan)
    if not planned['release']:
        print('No release inputs changed.')
        return
    tag = next_version(git(root, 'tag', '--list', 'v*').splitlines())
    output = root / 'build/release-tree'
    # A superseded run may have promoted an image tag before its atomic Git
    # push was rejected. Never replace that tag; allocate the next patch.
    for attempt in range(100):
        if output.exists(): shutil.rmtree(output)
        state = assemble(root, planned, args.artifacts, tag, source, output)
        try:
            publish_image_tags(state)
            break
        except ImageTagConflict:
            # A moved tag from a prior completed release is corruption, not a
            # reason to keep generating new catalog versions.
            if any(entry['image'].rsplit(':', 1)[1] != tag[1:]
                   and registry_digest(entry['image']) != entry['verified_image'].split('@', 1)[1]
                   for entry in state['images'].values()):
                raise
            tag = next_version([tag])
    else:
        raise ValueError('no unused image release version within 100 patches')
    generated = [path for path in output.rglob('*') if path.is_file()]
    for path in generated:
        target = root / path.relative_to(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    run(sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_catalog.py', '-v')
    run('git', 'config', 'user.name', 'github-actions[bot]')
    run('git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    run('git', 'add', '--', *[str(path.relative_to(output)) for path in generated])
    run('git', 'commit', '-m', f'chore: release {tag} [skip ci]')
    run('git', 'tag', '-a', tag, '-m', f'Squab templates {tag}')
    # A concurrent human push causes a non-fast-forward rejection of BOTH refs.
    # Never force-push or overwrite an existing release/tag.
    run('git', 'push', '--atomic', 'origin', 'HEAD:refs/heads/main', f'refs/tags/{tag}')
    publish_github_release(root, tag)


if __name__ == '__main__':
    main()
