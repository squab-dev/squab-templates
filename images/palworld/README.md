# Palworld

Palworld **1.0.5.102999**, linux/amd64. The official Pocketpair game payload is
pinned by digest in [runtime.Dockerfile](runtime.Dockerfile); Wolfi libraries and
Python are locked in [wolfi.lock.json](wolfi.lock.json). No Steam account,
SteamCMD installation or download-on-start is required. The image runs as
UID/GID 65532 with a read-only root filesystem and persistent saves in `/data`.

## Build and test

```sh
make check build GAME=palworld
make smoke GAME=palworld
```

Docker is required during this build. The final image is loaded as
`squab-palworld:verify-amd64`; unlike the runtime-only images, no duplicate large
image archive is retained. Allow at least 30 GiB free build space for the
upstream image, intermediate layers and final image. The smoke test boots a
real empty world, checks the authenticated game API, sends `stop` through stdin,
recreates the container and verifies the same world identifier. Its temporary
6 GiB memory limit is for the empty-world test, not the hosting recommendation.

## Squab catalog

Release automation fills [template.json](template.json) with the verified image
digest and adds it to `catalog.json`. Deploy the Core/Wing implementation of
**protocol 1.5** and selected `game.container-health.v1` before releasing this
template. Core refuses placement on older agents. Ordinary later image changes
need only a catalog release.

The template reserves UDP 8211, 16 GiB RAM, 16 GiB persistent storage and four
CPU cores. The shared image also consumes space in Docker's node-wide image
store, outside the server's save quota. Larger worlds may need more than 32 GiB
RAM. Only gameplay is exposed; do not publish management port 8212 or RCON.

The initial server name and player limit are creation-only fields. Other game
settings can be edited in `/data/Config/LinuxServer/PalWorldSettings.ini` while
stopped. The launcher preserves gameplay options and always manages the server
name, player limit, authenticated mode and management API settings. It rotates
the internal API password at startup. Passwords are not printed or passed in
process arguments; the launcher's copy is kept in temporary storage.

Console commands: `save` and `stop`. The adapter calls the authenticated REST
save/shutdown endpoints and waits for the actual game process to exit. Docker
SIGTERM/SIGINT request the same shutdown. Wing's timeout remains responsible
for forced termination. Backups must be made while stopped.

## Local Compose

Set `PALWORLD_IMAGE` to the published digest reference, then:

```sh
docker compose up -d
docker compose logs -f
docker compose stop
```

The named volume retains saves across container recreation. Back it up before
selecting a new image digest; older game versions may not read upgraded worlds.

## Sources and verification boundary

- [Pocketpair's official image](https://github.com/pocketpairjp/palworld-dedicated-server-docker)
- [Server requirements](https://docs.palworldgame.com/getting-started/requirements/)
- [Startup arguments](https://docs.palworldgame.com/settings-and-operation/arguments/)
- [REST API](https://docs.palworldgame.com/api/rest-api/palwold-rest-api/)

Local testing proves server boot, API readiness, persistence and graceful stop.
A real player joining through a deployed Squab UDP gateway remains a separate
operator acceptance check.
