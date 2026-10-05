# Hytale owner sign-in (2026-10-05)

Task: https://github.com/squab-dev/squab-docs/issues/16

The catalog template uses Hytale 0.6.8 and a public bootstrap pinned by HTTPS URL,
110,451,990 bytes and SHA-256 `dcd2956cc65b950084650eadd56b889cf51f7610c127c3daac1f74dc471fec97`.
The final image contains only locked Wolfi packages, launchers, metadata and the
compiled Squab readiness plugin. Public SDK files stay in the build environment;
no Hytale game payload or account credential enters image layers, CI or catalog.

The owner authorizes a native device login at runtime. The installer downloads
its own authenticated payload, persists encrypted authorization under the server
volume and migrates it into `game/Server`. The launcher verifies the exact server
version, records JAR/assets hashes and checks those on restart. The image's
loopback plugin requires a ready world and a valid authenticated session.

Completed local acceptance:

- Unit/release tests cover input boundaries, profile selection, download size/hash,
  redirects, symlinks, changed files, installation receipts and authentication
  sequencing. The public SDK compiles the readiness plugin.
- Real non-root Docker bootstrap passed with a read-only root, dropped
  capabilities, 64 MiB tmpfs and no account. No game assets were installed and
  readiness remained false until authorization.
- The user authorized one isolated test server. Native installation downloaded
  Hytale 0.6.8, started a real world and preserved encrypted credentials with
  owner-only file permissions.
- Recreating the container with the verified image loaded `Squab:Readiness`,
  became Docker-healthy without another browser login, and retained the same
  world UUID and seed.
- Native `auth logout` made the health probe fail. Native console `stop` exited
  successfully; SIGTERM also exited successfully. No forced kill was needed.
- Trivy 0.74.0 found zero fixable HIGH/CRITICAL vulnerabilities in the image.
- Test credentials, downloaded game payload, world, container and private test
  logs were removed after validation. They were never in the repository/build
  context. CI runs only the account-free smoke.

A real player connection through the deployed UDP gateway remains unverified.
The local smoke validates game/API readiness and persistence, not a client join.
First-start authentication and download must fit the 900-second Wing deadline;
users restart to obtain a fresh expired device prompt. No automatic game upgrade
or template migration is implemented.
