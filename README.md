# Squab templates

Minimal, curated game runtime images and Core catalog metadata. The first image
is Paper 26.2 build 123, using apko, Wolfi OpenJDK 25 and the existing Squab
launcher contract. Initial platform: **linux/amd64**.

## Layout

```text
images/
  paper/
    apko.yaml                 # image composition and non-root identity
    wolfi.lock.json            # reviewed remote APK versions and checksums
    melange.yaml              # package the launcher for apko
    squab-paper-launcher       # no downloader or customer shell hooks
    template.json             # metadata; intentionally lacks an image digest
tools/                        # shared build, lock, render and smoke tools
tests/                        # launcher and release tooling regression tests
api/vendor/                   # template schema, specification version and hashes
.github/workflows/paper.yml   # only Paper/shared build changes trigger it
```

Add future games as sibling directories with their own workflow path filters.
Shared tooling changes rebuild all workflows that use those tools. Each image
owns its configuration, dependency lock and versioned launcher package.

## Build

Linux amd64 requires Python 3, bubblewrap, apko 1.4.1 and melange 0.60.0.
Use locally installed versions or `make tools` to install checksum-verified
releases under `.tools/bin`, then add that directory to PATH.

```sh
python3 -m pip install -r requirements-dev.txt
make check build
docker load -i build/paper/image.tar
make smoke
# Podman is supported: CONTAINER_ENGINE=podman make smoke
```

Build output and ephemeral APK signing keys stay in ignored `build/`. apko
generates the image and SPDX SBOM. The committed lock freezes all runtime Wolfi
packages, including transitive dependencies; only the locally built launcher
entry is replaced for each build. A changed apko config requires an explicit
lock update. To update dependencies, run `apko lock` using the build repository
and public key from `tools/build.sh`, remove only the local launcher entry from
the resulting lock, and review the remaining version/checksum changes before
replacing `images/paper/wolfi.lock.json`.

The launcher is packaged from source with melange; its build environment is
resolved from Wolfi, while the final runtime dependencies are locked. Rebuilds
can have different provenance/signature metadata; the build does not promise
identical image digests across different source commits or signing keys.

## CI and catalog integration

Pull requests build, smoke-test and scan Paper without publishing. Changes on
`main` build and publish the verified image as
`ghcr.io/squab-dev/squab-templates/paper:sha-<commit>`. The workflow records the real
registry digest and uploads a matching immutable `template.json` and SBOM.
No mutable tag or example digest is used in a catalog manifest. Each image
digest produces a stable, distinct revision UUID.

On the Core operator host, after the required release acceptance, use the normal
operator environment (database URL, operator identity/token and registry
allowlist including `ghcr.io`):

```sh
core-operator catalog validate --manifest template.json
core-operator catalog publish --manifest template.json
```

This uses Core's existing authenticated operator path and audit trail. The Panel
queries `/api/v1/templates`, follows pagination, and refreshes every 60 seconds
while the game-selection step is visible, on returning to the tab, or when
the user clicks **Refresh games**. It retains the last list on failures. If a
selected revision changes, it requires an explicit new selection rather than
combining old configuration with a new revision.

Image publication does not automatically publish a customer catalog entry.
The existing specification requires operator/legal review and real Paper client,
world persistence, backup/restore and resource acceptance before public catalog
publication. Those acceptance steps are not claimed by the image smoke test.

## Runtime contract

UID/GID 65532, `/data` working directory, port 25565/TCP, Java heap capped at 75%
of container memory. Wing validates the explicit Minecraft EULA acceptance,
fetches the exact checksum-pinned artifact and mounts `/squab-runtime` read-only.
The image contains no Paper JAR. The launcher checks the artifact again, rejects
customer Java options and unsupported protected variables, requires Wing's
configuration, preserves online authentication and executes Java directly.

This repository follows specification 0.3.5's manifest/API contract. The user's
2026-09-16 apko/Wolfi packaging choice supersedes the earlier Corretto image
choice for this new image; the legacy Wing image remains historical evidence.
