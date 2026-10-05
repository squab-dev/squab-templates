# Hytale runtime image

A minimal Wolfi Java 25 runtime and Squab launcher, built with the same apko /
melange tooling as Paper. Runs as UID/GID 65532, with persistent state in `/data`.
Initial architecture: linux/amd64. It contains no Hytale server files, downloader,
account credentials or update wrapper. The image requires separately obtained
server files; it is not yet a one-click Squab catalog template.

## Build

From the repository root:

```sh
make tools
export PATH="$PWD/.tools/bin:$PATH"
make check build GAME=hytale
docker load -i build/hytale/image.tar
make smoke GAME=hytale
```

The shared release workflow builds Hytale when its inputs change and publishes
verified images on main as
`ghcr.io/squab-dev/squab-templates/hytale:sha-<commit>` and uploads the immutable
image reference and SBOM. Production deployments must use that digest reference.
Other runtime images retain their existing digest when unchanged. No Hytale catalog entry is
emitted: Core/Wing still need multi-file distribution, authentication integration,
configuration and readiness support for this game.

## Supply the runtime and start

Obtain `Server/HytaleServer.jar` and `Assets.zip` from the same Hytale release using
the official authenticated downloader or an existing authorized installation.
Keep a record of that release. Copy only those two files into `runtime/` next to
[compose.yaml](compose.yaml). Do not put credentials, game files or worlds in Git.

```sh
mkdir -p runtime data
# Copy the matching HytaleServer.jar and Assets.zip into runtime/ first.
sudo chown -R 65532:65532 data
chmod 755 runtime
chmod 644 runtime/HytaleServer.jar runtime/Assets.zip
export HYTALE_SERVER_SHA256=$(sha256sum runtime/HytaleServer.jar | cut -d' ' -f1)
export HYTALE_ASSETS_SHA256=$(sha256sum runtime/Assets.zip | cut -d' ' -f1)
export HYTALE_IMAGE='ghcr.io/squab-dev/squab-templates/hytale@sha256:<published-digest>'
docker compose up -d
docker compose attach hytale
```

The hashes record your selected files; they do not independently authenticate a
download. The launcher verifies both at every start. The Compose example mounts
runtime files read-only, persists `/data`, and allows UDP 5520. Change the **host**
port mapping for additional instances. It allocates 6 GiB RAM and 3 CPU cores;
adjust those to your host and workload. Heap defaults to 75% of the container limit.
There is no TCP-based health check: QUIC readiness needs a game-aware probe.

At the server console run `/auth login device`, complete the browser flow, and
check `/auth status`. Use Docker's detach sequence Ctrl-P, Ctrl-Q to leave the
console without stopping it. `/auth persistence Encrypted` enables the server's
own persistent credential store; preserve `/data` and test authentication after
container recreation. Provider-managed session tokens can instead be supplied
through the official `HYTALE_SERVER_SESSION_TOKEN` and
`HYTALE_SERVER_IDENTITY_TOKEN` environment variables using your secret manager.
The image does not obtain or store provider refresh tokens for you.

## Configuration and updates

Edit the server-generated `config.json` under `data/` while stopped. The launcher
accepts `HYTALE_PORT` (1–65535, default 5520), `HYTALE_HEAP_PERCENT` (25–85,
default 75), and `HYTALE_RUNTIME_DIR` (absolute, default `/squab-runtime`).
It requires both SHA-256 variables above. It always uses authenticated mode and
sets `HYTALE_DISABLE_UPDATES=true`. JVM injection variables and extra command-line
arguments are rejected; there is no shell evaluation of custom arguments.

Stop the server, back up `/data`, obtain a matching new JAR/assets pair, update
both checksums, then recreate it. There are no downloads, automatic file mutation,
or restart-for-update loops in the launcher. AOT cache is deliberately omitted
because its compatibility with the selected Wolfi JVM is not verified.

## Sources and verification limits

- [Official server manual](https://support.hytale.com/hc/en-us/articles/45326769420827-Hytale-Server-Manual)
- [Official provider authentication](https://support.hytale.com/hc/en-us/articles/45328341414043-Server-Provider-Authentication-Guide)
- [Referenced Docker example](https://github.com/indifferentbroccoli/hytale-server-docker)

The example informed the required runtime and console flow; this launcher is an
independent implementation. Unit tests simulate Java to check file integrity,
argument boundaries and authentication/update defaults. Container smoke tests
check the actual JVM, UID, writable state directory and fail-closed startup.
A licensed server boot, persistent authentication and real client connection need
operator-provided Hytale files/account and are not claimed by those tests.
