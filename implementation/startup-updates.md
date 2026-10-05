# Catalog versions, artwork and startup updates

Issue: https://github.com/squab-dev/squab-docs/issues/18
Contract specification 0.3.18.

Catalog assembly retains immutable historical manifests and release-specific image
references. Metadata/artwork changes reuse images; launcher changes rebuild only
that game. Official artwork provenance is recorded in artwork/README.md.

Paper checks stable builds for Minecraft 26.2, validates official URL/size/SHA-256,
and replaces cached JARs atomically. Real read-only, non-root container validation
started Paper build 130, gracefully stopped/restarted and retained world data and
a marker. Minecraft version remained 26.2. EULA and pinned bootstrap checks remain.

Hytale uses the owner's own saved sign-in and official updater, with a startup
readiness gate and recoverable two-file replacement. Recovery tests interrupt file
moves and cleanup and verify world/config/auth preservation. Bootstrap and plugin
compile/smoke pass in a real non-root/read-only container. The authenticated
startup/update flow was explicitly skipped at the user's request; no client
connectivity is claimed. The disposable sign-in container/volume were deleted.

Palworld remains on a pinned official payload and updates through published images.
SteamCMD requires 32-bit dependencies unavailable in the current Wolfi runtime;
restart-time Palworld updates are not implemented in this release.

Validation: 46 Python tests and shell syntax checks; Paper/Hytale image builds and
smokes. CI scans changed images before automatic publication. Credentials and game
payloads are absent from the Hytale image and public catalog.
