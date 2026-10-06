# Squab templates

Game runtime images and versioned catalog manifests for Squab. Each runtime owns
its launcher, dependencies and usage instructions; shared tooling builds, verifies
and releases the catalog.

Browse [`images/`](images/) for the available runtimes and their documentation.
Use the [latest release](https://github.com/squab-dev/squab-templates/releases/latest)
for a published catalog, or [`catalog.json`](catalog.json) for the current index.
Supported versions, requirements, authentication and update behavior belong in each
runtime's README and release manifest.

## Repository layout

```text
images/<runtime>/             # runtime source and usage documentation
  apko.yaml                   # image composition and non-root identity
  wolfi.lock.json             # reviewed dependency versions and checksums
  melange.yaml                # launcher package build
  runtime.Dockerfile          # optional additional image composition
  template.json               # catalog metadata without an image reference
  README.md                   # runtime-specific instructions
artwork/                      # catalog artwork and source attribution
tools/                        # shared build, verification and release tooling
tests/                        # runtime, catalog and release regression tests
api/vendor/                   # pinned template contract and provenance
releases/<runtime>/<version>.json # immutable published manifests
catalog.json                  # release-generated index of published revisions
release-state.json            # fingerprints and references from the last release
```

## Build and verify

Use Linux amd64 with Python 3, bubblewrap and Docker. Install the pinned build
tools with mise:

```sh
mise use -g apko@1.4.6 melange@0.61.2
python3 -m pip install -r requirements-dev.txt
make check
```

Alternatively, `make tools` installs checksum-verified tools in `.tools/bin`;
add that directory to `PATH` before building.

Choose a directory from `images/` and use its name in place of `<runtime>`:

```sh
make build GAME=<runtime>
```

When the build produces `build/<runtime>/image.tar`, load it with
`docker load -i build/<runtime>/image.tar`. Composed images are loaded by the build
script directly. Run `make smoke GAME=<runtime>` afterward. Follow that runtime's
README for setup, persistent storage, launch requirements and additional checks.

Build output, SBOMs and ephemeral package-signing keys stay in ignored `build/`;
signing keys are never published. Runtime dependencies are locked, including
transitive packages. Changes to image composition require a reviewed lock update;
launcher-only changes can retain the existing remote package pins.

## Releases and selective builds

Pull requests validate the catalog and release tooling, then build, smoke-test
and scan affected images. On `main`, verified image or template changes publish
a new patch tag and GitHub Release automatically.

| Change since the last release | Image builds | New release |
| --- | --- | --- |
| Runtime launcher, composition or dependency lock | Changed runtime only | Yes |
| Shared build tools or image workflow | All affected runtimes | Yes |
| Template metadata | None; reuse the published image version | Yes |
| Catalog/release tooling or contract | None | Yes |
| Documentation, tests or local Compose examples | None | No |

The release planner compares fingerprints with `release-state.json`. Failed or
superseded runs leave changes pending; unchanged images retain their published
version tags. Each rebuilt image must pass its smoke checks and the scan for fixable
HIGH/CRITICAL vulnerabilities before publication.

The release job promotes verified images to stable `MAJOR.MINOR.PATCH` tags. It
checks registry contents before reusing a tag and never overwrites a different
image. Build digests remain verification evidence in `release-state.json`.
Unchanged images keep their previous version tag. Historical digest-based
manifests remain available; new tags require Core and Wing protocol 1.7 support.

The release job generates new immutable manifests, `catalog.json` and
`release-state.json`, commits them to `main`, and atomically pushes an annotated
tag at that commit. Generated commits do not trigger another release. A newer
source commit causes an obsolete release run to defer instead of overwriting it.

Each release includes `catalog.json`, `release-state.json`, and `catalog.tar.gz`
containing the index and all referenced manifests. SBOMs and build evidence are
available in workflow artifacts. If publication fails after the tag/catalog push,
rerun that source workflow: it resumes the release without rewriting published
revisions or rebuilding unchanged images.

Do not edit generated catalogs or historical manifests by hand. Edit a runtime's
`template.json`; changed content receives a distinct revision identifier. The
catalog retains published history for image-version selection. Existing servers
keep their selected image until explicitly upgraded.

## Catalog consumers

Configure Squab Core to import this public index periodically:

```text
https://raw.githubusercontent.com/squab-dev/squab-templates/main/catalog.json
```

Replace `main` with a release tag to pin the catalog. Use raw repository URLs for
Core; release-asset downloads redirect and are incompatible with its strict
fetcher. To use another approved HTTPS origin, extract `catalog.tar.gz` and keep
its relative directory layout.

Enable catalog sync in the Squab Helm configuration. Public catalogs need no
GitHub token. Core retains existing entries if a fetch fails and rejects changed
content for an existing revision. Compatible runtimes and image versions are
discovered without editing Core or restarting it; new runtime capabilities can
require updated platform services. The vendored contract records the supported
specification version.

Catalog metadata supplies image version tags, artwork, resource requirements and any
license or artifact declarations. Container-image upgrades and game updates are
separate: supported runtimes may update game files at startup, while the selected
container image stays pinned. Check the runtime's own README for its policy and
limitations. Account credentials belong in private per-server data, never in
images or catalog metadata.

## Adding a runtime

Add a directory under `images/` with its composition, reviewed dependency lock,
launcher package, smoke checks and usage documentation. Register it in the shared
build and verification tools where required; the workflow discovers image
directories through their `apko.yaml` files. Add catalog metadata and artwork only
when Core and Wing support the required runtime contract.

Keep runtime-specific names, versions and instructions in that directory. Adding
or updating a runtime should not require changing this README.

## Verification

Run `make check` for regression and syntax checks, plus the affected runtime's
build and smoke checks. Run `actionlint` after workflow changes. Release tooling
tests cover selective builds, version reuse, digest verification, immutable history, failed-run recovery
and self-contained catalog archives. Release-specific validation and limitations
belong in [`implementation/`](implementation/) and the release/PR notes.
