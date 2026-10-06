# Hytale with owner sign-in

The Squab Hytale image contains Java 25, a setup launcher and a small readiness
plugin. It contains **no account credentials, server JAR or game assets**.
Each server owner signs in through Hytale's official browser flow. No shared
provider account or account token is required in CI, the image or the catalog.

## First start in Squab

1. Create a Hytale server and open its Console while it starts.
2. Open the official Hytale device URL shown there and sign in to your own account.
3. Wait for the game files to download and the world to start. The server becomes
   ready only after its world and authenticated session are available.

The launcher fetches the public bootstrap JAR pinned by URL, byte count and
SHA-256 in `bootstrap.json`. Hytale's own installer handles authenticated game
downloads. The launcher rejects any downloaded server release older than 0.6.8,
records hashes for the installed JAR/assets pair, and checks them on later boots.
Automatic game updates are disabled during normal operation.

The device code is valid for about 10 minutes (the console shows the exact
expiry). The JVM logs `Failed to get Hardware UUID` inside containers; the
encrypted credential store then uses the `auth.key` it keeps in `/data/game`,
so sign-in still survives container recreation.

Setup, game files, worlds and Hytale's encrypted credential store stay in this
server's persistent `/data/game`. Credentials never become image layers or
catalog metadata. Treat server files and backups as private: they include that
server's authorization. Browser/device codes expire; restart to obtain a new
prompt. Squab's startup deadline is 15 minutes, including authentication and
download time. Cached valid files are reused after a restart.

If the account has multiple game profiles, stop the server and create
`game/profile.json` through Files with `{"uuid":"your-profile-uuid"}` before
starting again. The console lists available profiles. Existing authenticated
sessions use their saved profile; changing accounts requires `auth logout` in
the running server console followed by restart and browser sign-in.

Edit generated game configuration under `game/Server` while stopped. The
configuration API is not advertised by this template. Gameplay uses UDP 5520;
the readiness endpoint is loopback-only and is never allocated as a game port.
The template reserves at least 6 GiB RAM, 16 GiB disk and 3 CPU cores. Heap uses
75% of the container memory limit by default.

## Build and standalone use

```sh
make tools
export PATH="$PWD/.tools/bin:$PATH"
make check build smoke GAME=hytale
```

The build downloads the public pinned JAR only to compile Squab's readiness
plugin; only the compiled plugin enters the image. The final image is loaded by
the build script, and the complete-image SBOM includes its locked Wolfi runtime.

For Compose, create `data/`, make it writable by UID/GID 65532, and set
`HYTALE_IMAGE` to the published digest reference:

```sh
mkdir -p data
sudo chown 65532:65532 data
export HYTALE_IMAGE='ghcr.io/squab-dev/squab-templates/hytale@sha256:<digest>'
docker compose up -d
docker compose logs -f hytale
```

Open the displayed browser link. The container runs with a read-only root,
dropped capabilities and a persistent data mount. Native JVM scratch files live
inside that server's data directory. Optional standalone settings are
`HYTALE_PORT`, `HYTALE_HEAP_PERCENT` and `HYTALE_OWNER_UUID`; credentials and
arbitrary JVM arguments are rejected. The previous external-runtime launcher
remains at `/usr/local/bin/squab-hytale-launcher` for explicitly configured
standalone deployments, but it is not used by the catalog template.

## Updates and verification

Existing servers retain their template/image revision. Back up server data
before an explicit version migration; replacing just one installed game file
fails integrity validation. This implementation does not silently upgrade game
files or claim that a newer release can read existing worlds.

Automated checks cover launch settings, download and installed-file integrity,
no-token injection, a real unprivileged bootstrap reaching browser sign-in,
unauthenticated readiness, and graceful stop. A licensed game download, world
boot, persistent authentication and real client connection additionally require
an owner-authorized test server. See [implementation evidence](../../implementation/hytale-image.md)
for completed checks and outstanding acceptance.

Sources: [official server manual](https://support.hytale.com/hc/en-us/articles/45326769420827-Hytale-Server-Manual),
[provider authentication guide](https://support.hytale.com/hc/en-us/articles/45328341414043-Server-Provider-Authentication-Guide).

## Snapshots

The template offers stopped backups only. Hytale 0.6.8 has `world save --all`
(logs `Finished saving all worlds`) and a per-world chunk-saving toggle, but no
command that pauses every writer for the whole universe: player, entity and
world-resource saves keep running, so a copy taken while the server runs is not
guaranteed to be consistent. Its native `backup` command needs `--backup-dir`
and writes its own archive, which does not fit Wing's copy-then-resume model.
Adding `live_snapshot` needs an owner-authorized world to prove a restore.

## Updates on restart

Every startup checks Hytale's official release channel using this server owner's
saved sign-in. The readiness plugin stages and verifies a new release, asks the
native server to shut down for update, then the wrapper replaces only the JAR and
assets using a recoverable journal. Worlds, configuration, mods and encrypted
authentication stay in the private data volume. Background automatic application
is disabled; updates happen during startup. Failed checks remain visibly unhealthy
and can be retried by restarting. No account material is included in the image.
The public bootstrap and plugin SDK remain pinned at 0.6.8; compatible newer stable
game releases are supported. Plugin incompatibility prevents readiness.
