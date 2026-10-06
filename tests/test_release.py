"""Incremental releases preserve immutable metadata and skip unrelated images."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import release

spec = importlib.util.spec_from_file_location('publisher', ROOT / 'tools/publish-release.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def image(game, digest='0123456789abcdef' * 4):
    return f'ghcr.io/squab-dev/squab-templates/{game}@sha256:{digest}'


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        # Build an isolated release history. Copying the live catalog makes this
        # fixture collide with v0.2.1 as soon as the real workflow publishes it.
        for name in ('images', 'tools', '.github', 'api'):
            shutil.copytree(ROOT / name, self.root / name,
                            ignore=shutil.ignore_patterns('__pycache__', '.env', 'data', 'runtime'))
        for name in ('.gitignore', 'README.md', 'Makefile', 'requirements-dev.txt'):
            shutil.copyfile(ROOT / name, self.root / name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        self.artifacts = Path(self.temp.name) / 'artifacts'
        for game in ('paper', 'hytale', 'palworld'):
            target = self.artifacts / f'image-{game}' / 'image-reference.txt'
            target.parent.mkdir(parents=True)
            target.write_text(image(game) + '\n')
        self.source = 'a' * 40
        self.install_release('v0.2.1')

    def assemble(self, version):
        output = Path(self.temp.name) / version
        state = release.assemble(self.root, release.plan(self.root), self.artifacts,
                                 version, self.source, output)
        return state, output

    def install_release(self, version):
        state, output = self.assemble(version)
        shutil.copytree(output, self.root, dirs_exist_ok=True)
        return state

    def edit(self, path):
        target = self.root / path
        target.write_text(target.read_text() + '\n# changed\n')

    def test_documentation_tests_and_ignored_local_data_do_not_release(self):
        for path in ('README.md', 'images/hytale/README.md', 'images/hytale/compose.yaml'):
            self.edit(path)
        (self.root / 'images/hytale/.env').write_text('LOCAL_ONLY=true')
        (self.root / 'tests').mkdir()
        (self.root / 'tests/test_extra.py').write_text('# test only')
        self.assertEqual(release.plan(self.root)['build'], [])
        self.assertFalse(release.plan(self.root)['release'])

    def test_each_game_change_only_rebuilds_its_own_image(self):
        for game in ('paper', 'hytale', 'palworld'):
            with self.subTest(game=game):
                path = self.root / f'images/{game}/squab-{game}-launcher'
                original = path.read_bytes()
                self.edit(str(path.relative_to(self.root)))
                self.assertEqual(release.plan(self.root)['build'], [game])
                path.write_bytes(original)

    def test_shared_build_change_rebuilds_all_images(self):
        self.edit('tools/build.sh')
        self.assertEqual(release.plan(self.root)['build'], ['hytale', 'palworld', 'paper'])

    def test_publisher_change_releases_without_rebuilding_images(self):
        self.edit('tools/publish-release.py')
        planned = release.plan(self.root)
        self.assertTrue(planned['release'])
        self.assertEqual(planned['build'], [])

    def test_metadata_change_reuses_image_but_has_distinct_immutable_revision(self):
        before = release.read_json(self.root / release.STATE)
        path = self.root / 'images/paper/template.json'
        template = release.read_json(path)
        template['name'] += ' updated'
        release.write_json(path, template)
        self.assertEqual(release.plan(self.root)['build'], [])
        self.assertTrue(release.plan(self.root)['release'])
        after, output = self.assemble('v0.2.2')
        old_path = before['images']['paper']['manifest']
        old = release.read_json(self.root / old_path)
        new = release.read_json(output / after['images']['paper']['manifest'])
        self.assertEqual(old['image'], new['image'])
        self.assertNotEqual(old['revision_id'], new['revision_id'])
        self.assertEqual(release.read_json(self.root / old_path), old)
        self.assertEqual(after['images']['hytale'], before['images']['hytale'])
        self.assertEqual(release.render_manifest(self.root, 'paper', new['image']), new)

    def test_catalog_retains_versions_and_artwork_does_not_rebuild(self):
        before = release.read_json(self.root / 'catalog.json')['manifests']
        path = self.root / 'images/paper/template.json'
        template = release.read_json(path)
        template['name'] += ' newer'
        release.write_json(path, template)
        state, output = self.assemble('v0.2.2')
        catalog = release.read_json(output / 'catalog.json')['manifests']
        self.assertTrue(set(before).issubset(catalog))
        self.assertIn(state['images']['paper']['manifest'], catalog)
        self.assertEqual(len(catalog), len(before) + 1)
        self.assertEqual(release.plan(self.root)['build'], [])
        (self.root/'artwork').mkdir()
        (self.root/'artwork/paper.webp').write_bytes(b'new artwork')
        self.assertEqual(release.plan(self.root)['build'], [])

    def test_missing_artifact_and_placeholder_digest_fail_closed(self):
        self.edit('images/paper/squab-paper-launcher')
        reference = self.artifacts / 'image-paper/image-reference.txt'
        reference.unlink()
        with self.assertRaises(FileNotFoundError):
            self.assemble('v0.2.2')
        reference.write_text(image('paper', '0' * 64))
        with self.assertRaisesRegex(ValueError, 'placeholder'):
            self.assemble('v0.2.2')

    def test_unreleased_changes_survive_newer_changes_and_a_failed_assembly(self):
        self.edit('images/paper/squab-paper-launcher')
        (self.artifacts / 'image-paper/image-reference.txt').unlink()
        with self.assertRaises(FileNotFoundError):
            self.assemble('v0.2.2')
        self.edit('images/hytale/squab-hytale-launcher')
        self.assertEqual(release.plan(self.root)['build'], ['hytale', 'paper'])

    def test_unchanged_manifest_path_is_carried_forward(self):
        before = release.read_json(self.root / release.STATE)
        self.edit('images/hytale/squab-hytale-launcher')
        after, output = self.assemble('v0.2.2')
        self.assertEqual(before['images']['paper'], after['images']['paper'])
        self.assertTrue((output / 'releases/hytale/0.2.2.json').exists())
        self.assertEqual(release.read_json(output / 'catalog.json')['manifests'],
                         [data['manifest'] for game, data in sorted(before['images'].items()) if data['manifest']] + ['releases/hytale/0.2.2.json'])

    def test_existing_release_path_cannot_be_overwritten(self):
        self.edit('images/paper/squab-paper-launcher')
        (self.artifacts / 'image-paper/image-reference.txt').write_text(image('paper', 'fedcba9876543210' * 4))
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            self.assemble('v0.2.1')

    def test_changed_inputs_after_plan_are_rejected(self):
        planned = release.plan(self.root)
        self.edit('images/paper/squab-paper-launcher')
        with self.assertRaisesRegex(ValueError, 'after planning'):
            release.assemble(self.root, planned, self.artifacts, 'v0.2.2', self.source,
                             Path(self.temp.name) / 'output')

    def test_catalog_archive_resolves_all_relative_manifest_paths(self):
        target = Path(self.temp.name) / 'assets'
        publisher.package_catalog(self.root, target)
        with tarfile.open(target / 'catalog.tar.gz') as archive:
            index = json.load(archive.extractfile('catalog.json'))
            for path in index['manifests']:
                manifest = json.load(archive.extractfile(path))
                self.assertEqual(manifest['image'], f'ghcr.io/squab-dev/squab-templates/{Path(path).parts[1]}:0.2.1')

    def test_release_images_use_tags_and_keep_verified_build_evidence(self):
        state = release.read_json(self.root / release.STATE)
        for game, entry in state['images'].items():
            self.assertEqual(entry['image'], f'ghcr.io/squab-dev/squab-templates/{game}:0.2.1')
            self.assertEqual(entry['verified_image'], image(game))

    def test_legacy_digest_images_gain_tags_without_rebuilding(self):
        before = release.read_json(self.root / release.STATE)
        for entry in before['images'].values():
            entry['image'] = entry.pop('verified_image')
        release.write_json(self.root / release.STATE, before)
        self.edit('tools/publish-release.py')
        self.assertEqual(release.plan(self.root)['build'], [])
        after, output = self.assemble('v0.2.2')
        for game, entry in after['images'].items():
            self.assertTrue(entry['image'].endswith(':0.2.2'))
            self.assertEqual(entry['verified_image'], image(game))
        self.assertTrue((output / 'releases/paper/0.2.2.json').exists())

    def test_promotion_is_idempotent_and_never_overwrites_another_image(self):
        state = release.read_json(self.root / release.STATE)
        expected = image('paper').split('@')[1]
        with patch.object(publisher, 'registry_digest', return_value=expected), patch.object(publisher, 'run') as run:
            publisher.publish_image_tags(state)
            run.assert_not_called()
        with patch.object(publisher, 'registry_digest', return_value='sha256:' + 'a' * 64), patch.object(publisher, 'run') as run:
            with self.assertRaises(publisher.ImageTagConflict):
                publisher.publish_image_tags(state)
            run.assert_not_called()
        count = len(state['images'])
        with patch.object(publisher, 'registry_digest', side_effect=[None] * count + [expected] * count), patch.object(publisher, 'run') as run:
            publisher.publish_image_tags(state)
            self.assertEqual(run.call_count, count)
            for call in run.call_args_list:
                self.assertIn('--prefer-index=false', call.args)

    def test_version_uses_highest_stable_tag(self):
        self.assertEqual(release.next_version(['v0.2.9', 'v0.2.10', 'v0.3.0-rc.1']), 'v0.2.11')

    def test_failed_release_api_can_recover_from_existing_tag(self):
        for args in (('config', 'user.name', 'Test'), ('config', 'user.email', 'test@example.invalid'),
                     ('add', '.'), ('commit', '-qm', 'Release'), ('tag', 'v0.2.1')):
            release.git(self.root, *args)
        self.assertEqual(release.recovery_tag(self.root, self.source), 'v0.2.1')
        self.assertEqual(release.recovery_tag(self.root, 'b' * 40), '')

    def test_published_release_is_not_modified_on_retry(self):
        completed = subprocess.CompletedProcess([], 0, '{"isDraft": false}', '')
        with patch.object(publisher.subprocess, 'run', return_value=completed) as execute:
            publisher.publish_github_release(self.root, 'v0.2.1')
        self.assertEqual(execute.call_count, 1)

    def test_failed_upload_leaves_draft_unpublished(self):
        existing = subprocess.CompletedProcess([], 0, '{"isDraft": true}', '')
        failed = subprocess.CalledProcessError(1, ['gh', 'release', 'upload'])
        with patch.object(publisher.subprocess, 'run', side_effect=[existing, failed]) as execute:
            with self.assertRaises(subprocess.CalledProcessError):
                publisher.publish_github_release(self.root, 'v0.2.1')
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(execute.call_args.args[0][:3], ('gh', 'release', 'upload'))

    def test_publish_and_retry_use_one_atomic_catalog_commit_and_tag(self):
        self.check_atomic_publication()

    def test_orphaned_image_tag_allocates_next_patch_without_overwriting(self):
        self.check_atomic_publication(orphaned=True)

    def check_atomic_publication(self, orphaned=False):
        # Real git refs and publisher process with isolated GitHub/registry fakes.
        # No network, registry credentials or public refs are involved.
        tests = self.root / 'tests'
        tests.mkdir()
        shutil.copyfile(ROOT / 'tests/test_catalog.py', tests / 'test_catalog.py')
        for args in (('config', 'user.name', 'Test'), ('config', 'user.email', 'test@example.invalid'),
                     ('add', '.'), ('commit', '-qm', 'Baseline'), ('tag', '-a', 'v0.2.1', '-m', 'Baseline')):
            release.git(self.root, *args)
        remote = Path(self.temp.name) / 'remote.git'
        subprocess.run(['git', 'init', '-q', '--bare', str(remote)], check=True)
        release.git(self.root, 'remote', 'add', 'origin', str(remote))
        self.edit('images/paper/squab-paper-launcher')
        release.git(self.root, 'commit', '-qam', 'Update Paper launcher')
        source = release.git(self.root, 'rev-parse', 'HEAD')
        release.git(self.root, 'push', '-q', 'origin', 'HEAD:refs/heads/main', '--tags')
        planned = Path(self.temp.name) / 'plan.json'
        release.write_json(planned, release.plan(self.root))
        fake = Path(self.temp.name) / 'bin'
        fake.mkdir()
        gh = fake / 'gh'
        gh.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
state = Path(os.environ['TEST_GH_STATE'])
args = sys.argv[1:]
if args[:2] == ['release', 'view']:
    if not state.exists(): sys.exit(1)
    print(state.read_text())
elif args[:2] == ['release', 'create']:
    state.write_text('{"isDraft":true}')
elif args[:2] == ['release', 'upload']:
    failed = state.with_suffix('.failed')
    if not failed.exists():
        failed.touch()
        sys.exit(1)
    if not all(Path(arg).is_file() for arg in args[3:] if not arg.startswith('--')):
        sys.exit(2)
elif args[:2] == ['release', 'edit']:
    state.write_text('{"isDraft":false}')
else:
    sys.exit(3)
''')
        gh.chmod(0o755)
        docker = fake / 'docker'
        docker.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
state = Path(os.environ['TEST_REGISTRY_STATE'])
refs = json.loads(state.read_text()) if state.exists() else {}
args = sys.argv[1:]
if args[:3] == ['buildx', 'imagetools', 'inspect']:
    if args[3] not in refs:
        print('manifest not found', file=sys.stderr)
        sys.exit(1)
    print(json.dumps({'digest': refs[args[3]]}))
elif args[:3] == ['buildx', 'imagetools', 'create']:
    tag = args[args.index('--tag') + 1]
    assert tag not in refs
    refs[tag] = args[-1].split('@')[1]
    state.write_text(json.dumps(refs))
else: sys.exit(3)
''')
        docker.chmod(0o755)
        api_state = Path(self.temp.name) / 'gh.json'
        registry_state = Path(self.temp.name) / 'registry.json'
        orphaned_tag = 'ghcr.io/squab-dev/squab-templates/paper:0.2.2'
        orphaned_digest = 'sha256:' + 'b' * 64
        if orphaned:
            existing = {entry['image']: entry['verified_image'].split('@')[1]
                        for entry in release.read_json(self.root / release.STATE)['images'].values()}
            existing[orphaned_tag] = orphaned_digest
            release.write_json(registry_state, existing)
        env = dict(os.environ, GITHUB_REF='refs/heads/main', GITHUB_EVENT_NAME='push',
                   GITHUB_SHA=source, TEST_GH_STATE=str(api_state),
                   TEST_REGISTRY_STATE=str(registry_state),
                   PATH=str(fake) + os.pathsep + str(Path(sys.executable).parent)
                   + os.pathsep + os.environ['PATH'])
        command = [sys.executable, 'tools/publish-release.py', '--plan', str(planned),
                   '--artifacts', str(self.artifacts)]
        first = subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True)
        self.assertNotEqual(first.returncode, 0)
        self.assertTrue(release.read_json(api_state)['isDraft'], first.stderr)
        tag = release.recovery_tag(self.root, source)
        self.assertEqual(tag, 'v0.2.3' if orphaned else 'v0.2.2')
        if orphaned:
            self.assertEqual(release.read_json(registry_state)[orphaned_tag], orphaned_digest)
            self.assertFalse((self.root / 'releases/paper/0.2.2.json').exists())
        commit = release.git(self.root, 'rev-parse', f'{tag}^{{commit}}')
        self.assertEqual(release.git(remote, 'rev-parse', 'main'), commit)
        self.assertEqual(release.read_json(self.root / release.STATE)['source'], source)
        second = subprocess.run(command, cwd=self.root, env=env, capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertFalse(release.read_json(api_state)['isDraft'])
        self.assertEqual(release.git(remote, 'rev-parse', 'main'), commit)
        self.assertEqual(release.git(remote, 'tag', '--list').splitlines(), ['v0.2.1', tag])
        archive = self.root / 'build/release-assets/catalog.tar.gz'
        self.assertTrue(archive.exists())
