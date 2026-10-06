# Paper runtime

Minimal Wolfi OpenJDK 25 runtime for **Paper 26.2**. Build it with
`make build GAME=paper` and run `make smoke GAME=paper` from the repository root.
The Core template source is [template.json](template.json); the release workflow
adds the verified image digest and immutable revision identifier.

## Runtime contract

The image runs as UID/GID 65532 with `/data` as its working directory and port
25565/TCP. Java heap is capped at 75% of container memory. The image contains the
Squab launcher and updater, with no Paper JAR.

Wing validates explicit Minecraft EULA acceptance, downloads the exact pinned
artifact and mounts `/squab-runtime` read-only. The launcher verifies the file's
size and SHA-256 again. Before starting Java it queries the official Fill API for the latest stable build of Minecraft 26.2, verifies its size/SHA-256 and atomically caches it under `/data/.paper-runtime`. Every start/restart checks again, while the Minecraft version stays fixed. Failed checks stop startup visibly and preserve installed files. It requires Wing's configuration,
rejects customer Java options and unknown protected variables, preserves
`online-mode=true`, and writes EULA acceptance only from Wing's trusted signal.

The bootstrap artifact is `paper-26.2-129.jar`, published
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

## Live snapshots

The template declares `live_snapshot`. Wing sends `save-off`, then
`save-all flush` and waits for `Saved the game`, copies `/data` without `logs`,
`crash-reports` and `cache`, then sends `save-on`. Players stay connected.

## Real boot check

`python3 tools/boot-paper.py` runs the built image like Wing does (read-only
root, dropped capabilities, read-only `/squab-runtime` with the pinned JAR),
waits for a Minecraft status ping, runs the template's exact snapshot commands,
restores that copy into a fresh volume, boots it and checks that the world seed
comes from the restored `level.dat`, then stops both servers through the
console. It needs network access and no Minecraft account, so it does not
replace an authenticated client join.

The image version selector pins the container release, not a historical Paper build. Startup updates do not change the selected Minecraft version. Historical images keep their original behavior until explicitly upgraded.
