# Paper Wolfi implementation evidence

Verified 2026-09-16. User assignment: first minimal Paper template in
squab-templates, apko/Wolfi packaging, per-image CI and Panel catalog refresh.

## Checks

- apko 1.4.1 (locally installed) and melange 0.60.0; downloaded tool archives
  matched official SHA-256 checksums.
- `make check build`: launcher package and apko image built successfully.
- Three Python regression tests pass, including template schema validation,
  real-digest requirement, distinct immutable revisions, frozen remote lock
  entries and rejected untrusted launcher inputs.
- `CONTAINER_ENGINE=podman make smoke`: UID 65532; Java 25.0.4.1; missing trusted
  acceptance exits 64; missing artifact exits 65; writable data directory.
- Trivy 0.74.0 scan of the actual built image: zero fixable HIGH/CRITICAL
  vulnerabilities across 38 Wolfi OS packages. Scanner flags the private launcher
  APK namespace as non-Wolfi; it contains the reviewed shell source only.
- Actionlint 1.7.12 validates `.github/workflows/paper.yml`.
- Local tested image configuration ID:
  `sha256:f60cfbbb6cb455b9e5e87e2bc7aaa76f5c701bc0fc6cfba05dc267fb33a5fb70`.
  This is a local image ID, not a registry manifest digest for catalog import.

The workflow publishes only after tests and scan, records the real registry
manifest digest and emits the importable catalog manifest. No Paper JAR is
redistributed. Public catalog publication, authenticated client join, real world
persistence, backup/restore and full runtime resource acceptance remain separate
operator release checks and are not claimed by these smoke tests.

The first GitHub run passed build, smoke tests and scan but could not write the
legacy Wing-owned `squab-paper` package. The new repository uses its own
`ghcr.io/squab-dev/squab-templates/paper` package namespace instead.

## Published build

GitHub run https://github.com/squab-dev/squab-templates/actions/runs/35037136798
completed successfully: build, smoke tests, vulnerability scan, GHCR push and
catalog/SBOM upload. Source commit: `c7120efed39f365853fad56b1c21c75108fd99c2`.

Published reference:
`ghcr.io/squab-dev/squab-templates/paper@sha256:4d09c2439509d77867a6296bb6f8ac2de3c54739b2e739b781b136591e378191`.

The downloaded manifest passed the shared schema validator and is preserved in
`releases/paper/0.1.0.json` for the operator catalog import. It has not been
imported into any live Core database.
