# Squab templates

Curated game runtime images and versioned catalog manifests for Squab. Each game
owns its launcher, image composition and pinned dependencies; shared tools build,
verify and release them. Images run as a non-root user and target **linux/amd64**.

| Runtime | Image package | Core catalog |
| --- | --- | --- |
| [Paper](images/paper/README.md) | `ghcr.io/squab-dev/squab-templates/paper` | Minecraft Java 26.2, build 129 |
| [Palworld](images/palworld/README.md) | `ghcr.io/squab-dev/squab-templates/palworld` | Palworld 1.0.5.102999; requires Wing protocol 1.5 |
| [Hytale](images/hytale/README.md) | `ghcr.io/squab-dev/squab-templates/hytale` | Runtime image only; authenticated game files are supplied separately |

## Repository layout

```text
images/<game>/
  apko.yaml                   # image composition and non-root identity
  wolfi.lock.json              # reviewed remote APK versions/checksums
  melange.yaml                # launcher package build
  squab-<game>-launcher        # runtime entrypoint
  template.json               # optional Core metadata, without an image digest
  README.md                   # game-specific usage and constraints
tools/                        # shared build, release and verification tools
tests/                        # launcher, catalog and release regression tests
api/vendor/                   # pinned template schema and specification version
releases/<game>/<version>.json # immutable published manifests
catalog.json                  # release-generated index, latest revision per template
release-state.json            # generated after the first automated release
```

## Build and verify

On Linux amd64, install Python 3, bubblewrap and Docker (or Podman), plus apko
1.4.6 and melange 0.61.2. With mise:

```sh
mise use -g apko@1.4.6 melange@0.61.2
python3 -m pip install -r requirements-dev.txt
make check
make build GAME=paper
# Or: make build GAME=hytale
docker load -i build/paper/image.tar
make smoke GAME=paper
# Podman: CONTAINER_ENGINE=podman make smoke GAME=paper
```

`make tools` installs the same checksum-verified build tools under `.tools/bin`
for CI or environments without mise; add that directory to `PATH` before building.
Game files, launch requirements and Compose examples belong in each runtime's
README. Build output, SBOMs and ephemeral APK signing keys stay in ignored
`build/`; signing keys are never published.

The committed lock freezes all runtime Wolfi packages, including transitive
dependencies. Builds replace only the local launcher package entry. Changing
`apko.yaml` requires an explicit lock update: resolve with `apko lock` using the
local package repository/key produced by `tools/build.sh`, remove its local
launcher entry, and review the config checksum and remote package changes before
committing. A launcher-only package revision may keep the reviewed remote package
entries unchanged. The launcher build environment resolves from Wolfi; image
digests can differ across builds because of signing/provenance metadata.

## Automatic releases

Pull requests validate the catalog and release tooling, then build, smoke-test
and scan changed images. They do not publish packages or releases. On `main`,
successful image/template changes automatically publish the next patch tag and
GitHub Release (for example, `v0.2.0` → `v0.2.1`). README, tests and Compose-only
changes run checks without a new release when no earlier changes are pending.

| Change since the last release | Image builds | New release |
| --- | --- | --- |
| One game's launcher, apko config or dependency lock | That game | Yes |
| Shared build tools or image build workflow | All affected games | Yes |
| `template.json` metadata | None; reuse its published digest | Yes |
| Catalog/release tooling or schema | None | Yes |
| Documentation, tests or local Compose example | None | No |

The workflow compares input fingerprints against `release-state.json`, so failed
or superseded runs leave changes pending. The first automated release establishes
that state and builds both existing images. Later releases carry forward unchanged
image digests. Each built image must pass smoke checks and the HIGH/CRITICAL
fixed-vulnerability scan before it can enter a release. Verified images are pushed
to `ghcr.io/squab-dev/squab-templates/<game>:sha-<source-commit>`; catalog manifests
always use the actual registry digest.

The release job generates `catalog.json`, new immutable manifests and
`release-state.json`. It commits those files to `main` and atomically pushes an
annotated release tag at that commit. The workflow's `GITHUB_TOKEN` needs package
write access for builds and content write access for publication; branch rules
must permit the release bot's generated commit. The generated commit skips CI
and does not recursively trigger another release. A newer push to `main` causes
an obsolete release run to defer to the next run instead of overwriting it.

Each GitHub Release contains `catalog.json`, `release-state.json`, and
`catalog.tar.gz` with the index and referenced manifests in their relative paths.
The tag is an immutable source for the same catalog. SBOMs and build evidence are
available in workflow artifacts. If GitHub Release publication fails after the
tag/catalog push, rerun that source workflow: it resumes from the tag, repairs a
draft if needed, and does not rebuild or alter published revisions. The catalog
can be visible before the GitHub Release API step completes; its images have
already passed verification.

Do not hand-edit generated catalogs or historical manifests. Edit
`images/<game>/template.json`; a content change (including metadata with the same
image digest) gets a distinct deterministic revision UUID. The index contains one
current revision per supported template. Historical files remain available, and
existing servers retain their pinned revision.

## Catalog consumers

The public sync URL stays compatible with existing installations:

```text
https://raw.githubusercontent.com/squab-dev/squab-templates/main/catalog.json
```

For a fixed release, replace `main` with its tag. Use raw repository URLs for Core;
GitHub Release asset downloads redirect and are not compatible with Core's strict
catalog fetcher. Extract `catalog.tar.gz` to serve the same relative layout from
another approved HTTPS origin.

Core periodically imports the index when catalog sync is enabled in the Squab
Helm configuration (`catalog.enabled: true` with the operator Secret configured;
the default schedule is every five minutes). No GitHub token is needed for the public catalog. Core keeps
its existing entries on fetch failures and rejects changed content for an
existing revision. A new release does not upgrade running servers automatically.

This repository uses the template contract from specification **0.3.16**.
**Deploy Core 0.9.1 once before enabling this update** to remove its old Paper
build allowlist. After that, new compatible templates and image versions become
available through catalog sync without another Core release or restart. The
catalog owns image digests, artifact pins and license document versions; Core and
Wing enforce the supported runtime contract and verify integrity. New runtime
capabilities may still require service support. The launcher-only image
and Wing artifact verification continue to require explicit Minecraft EULA
acceptance. Hytale is not added to the catalog by this change.

## Adding a runtime

Add a directory under `images/` with its own apko configuration, reviewed lock,
melange launcher package, smoke checks and README. Extend the supported game
choices in the build/lock tools and Makefile smoke target. The workflow discovers
image directories from their `apko.yaml` files. Add `template.json` only when Core
and Wing implement the required runtime, license and readiness contracts.

## Verification

Release planner regression tests cover independent/shared image changes,
metadata-only revisions, digest reuse, failed-run carry-over, immutable history,
self-contained catalog archives and retrying GitHub Release publication. Run
`make check` and `actionlint` after changing the workflow or release tools.

Local verification on 2026-10-05: all 25 unit/regression tests and shell syntax
checks passed; actionlint passed; both Paper and Hytale built with apko 1.4.6 /
melange 0.61.2 and passed Docker smoke checks. The official Paper build-129 JAR
was downloaded and its exact size/checksum verified. Smoke checks exercise the
launcher contract; a real authenticated Minecraft client session was not run.
The PR workflow separately performs the required image vulnerability scans.
