# Paper runtime

Minimal Wolfi OpenJDK 25 runtime for **Paper 26.2 build 129**. Build it with
`make build GAME=paper` and run `make smoke GAME=paper` from the repository root.
The Core template source is [template.json](template.json); the release workflow
adds the verified image digest and immutable revision identifier.

## Runtime contract

The image runs as UID/GID 65532 with `/data` as its working directory and port
25565/TCP. Java heap is capped at 75% of container memory. The image contains the
Squab launcher, with no Paper JAR or downloader.

Wing validates explicit Minecraft EULA acceptance, downloads the exact pinned
artifact and mounts `/squab-runtime` read-only. The launcher verifies the file's
size and SHA-256 again before starting Java. It requires Wing's configuration,
rejects customer Java options and unknown protected variables, preserves
`online-mode=true`, and writes EULA acceptance only from Wing's trusted signal.

The selected artifact is `paper-26.2-129.jar`, published
`2026-09-23T18:49:01Z`, size **64,522,678 bytes**, SHA-256
`b1d8f6bfa1b6101fa8e947b53041cb3bdf5540e7b83b6547ca19ba7edefeb083`.
The official metadata is available from the
[Paper downloads service](https://fill.papermc.io/v3/projects/paper/versions/26.2/builds/129).
Keep the launcher and template pins in sync and verify the upstream artifact
when changing builds. Core 0.9.1 reads these pins from the catalog; future Paper
builds do not need a Core code change or release.

Historical build-123 manifests and images remain immutable. Existing servers
continue using their selected revision; publishing build 129 does not replace
their binary or world files.
