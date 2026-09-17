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

The public `catalog.json` index lists the committed release manifests to import.
Core 0.1.2 and squab-helm chart 0.3.0 can fetch it automatically on installation
and every five minutes (enable `catalog.enabled` and configure the existing
operator Secret). The default URL is
`https://raw.githubusercontent.com/squab-dev/squab-templates/main/catalog.json`.
The repository is public, so no GitHub token is needed. Core keeps existing
entries on fetch failures and rejects changed content for an existing revision.

To publish another curated release, commit the verified workflow's manifest to
`releases/<game>/<version>.json` and append that path to `catalog.json`, ordered
oldest to newest. Do not edit an already published revision; each new image
digest needs a new revision. `make check` validates the public index and all
referenced releases. Adding a release to this index authorizes deployment
operators who enabled sync to import it. Image builds still produce candidates;
only indexed releases enter the customer catalog after the required release
acceptance. This keeps experimental image builds out of running deployments.

The Panel queries `/api/v1/templates`, follows pagination, and refreshes every
60 seconds while game selection is visible, on returning to the tab, or when
the user clicks **Refresh games**. It retains the last list on failures. A new
indexed release normally appears within five minutes plus the Panel refresh.

Manual operator commands remain available (operator token on stdin):

```sh
core-operator catalog sync --index-url https://raw.githubusercontent.com/squab-dev/squab-templates/main/catalog.json
core-operator catalog ensure --manifest releases/paper/0.1.0.json
```

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
