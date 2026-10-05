# Palworld image and catalog

Adds Palworld 1.0.5.102999 from the official Pocketpair image digest
`sha256:78d5edea9214c5c76628ea3ad29935052f837489f7f73ffa37654da14ee37892`.
Copies only the game payload into a locked Wolfi/Python runtime, with UID/GID
65532, persistent `/data`, authenticated API health and stdin save/stop handling.
Game files are fixed by the image digest; startup performs no downloads.

Validation on 2026-10-05:

- 29 template/launcher/release tests, shell syntax and actionlint passed.
- The apko/melange plus Docker payload build completed locally.
- Real game smoke passed boot, API/world readiness, stdin graceful stop and world
  identity after container recreation. The final smoke uses Wing's 64 MiB tmpfs,
  read-only root, dropped capabilities and non-root UID.
- Trivy 0.74.0 reported zero fixable HIGH/CRITICAL vulnerabilities. Generated both
  apko SBOMs and a complete-image SPDX SBOM; CI repeats scanning before publishing.
- Compose configuration validates. The release planner detects all shared build
  changes in this transition. Per-game changes subsequently rebuild only that
  game; metadata-only releases reuse unchanged image digests.

The catalog uses `container_health` and requires Core/Wing protocol 1.5 support.
Roll those out before merging this template, since main automatically releases
and generates the catalog. No public digest or generated catalog is fabricated
on this branch. A real player connecting through deployed UDP ingress remains
unverified.

Hytale's existing Java runtime is unchanged. Its catalog entry is pending an
authorized matching server JAR/assets pair, authentication setup and game-aware
readiness validation. Shared health capability support alone does not provide
those missing game files or authenticate a server.
