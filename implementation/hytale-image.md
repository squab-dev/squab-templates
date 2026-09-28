# Hytale runtime image (2026-09-28)

Adds Hytale alongside Paper in squab-templates with the same apko/melange,
locked Wolfi Java 25 packages, non-root UID/GID 65532 and /data conventions.
The independent workflow builds, smoke-tests and scans the image on PRs, then
publishes immutable commit tags, digest reference and SBOM on main.

The independently authored launcher verifies operator-provided JAR/assets against
explicit SHA-256 values, fixes authenticated mode, disables automatic updates,
bounds port/heap settings and execs Java. No Hytale proprietary files, credentials,
downloader or provider tokens are baked into the image. Compose documents read-only
runtime mounts, persistent data, UDP 5520 and interactive authentication.

Validation:
- Eight unit tests pass, including Paper/catalog regression tests and Hytale file
  integrity, argument validation, update/auth defaults and lock merging.
- Actual apko/melange build succeeded for linux/amd64, producing an 87 MiB archive
  and SBOM. Runtime packages are pinned in wolfi.lock.json.
- Podman smoke test passed: UID 65532, real OpenJDK 25, writable /data, HOME=/data,
  executable launcher, no bundled artifacts and exit 64 for missing checksums.
- New workflow, Compose and build configurations parse as YAML; shell syntax and
  git diff checks pass. Trivy scanning remains a CI check, not a local pass.

A licensed Hytale server boot, account-auth persistence, native QUIC operation and
real-client connection are unverified without game files and an account. No
Hytale catalog entry is added: Core/Wing integration for multiple runtime files,
provider authentication and game-specific readiness remains separate work.

Sources: official Hytale Server Manual and Server Provider Authentication Guide,
linked in images/hytale/README.md; the user-provided indifferentbroccoli image was
reviewed as a reference, not copied. There are no production deployment changes.
