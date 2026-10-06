# CurseForge modpack runtime

Runs a Minecraft Java modpack from CurseForge. The server owner brings their own
CurseForge API key and names the modpack; the launcher downloads that modpack's
official **server pack** from CurseForge, verifies it, installs the pack's mod
loader from its official source and starts the server with the matching Java.

The image contains Squab's launcher, Python and four Wolfi OpenJDK runtimes
(8, 17, 21 and 25). It contains no Minecraft, loader, mod or modpack files and no
API key. Build it with `make build GAME=curseforge`, then `make smoke GAME=curseforge`.

## Configuration

| Field | Kind | Behaviour |
| --- | --- | --- |
| `CF_API_KEY` | required, **sensitive** | The owner's CurseForge API key. Write-only in Squab; delivered only as the file `/run/squab/secrets/CF_API_KEY` with `CF_API_KEY_FILE` naming it. |
| `CF_MODPACK` | required, create-only | Modpack project ID (`925200`), slug (`all-the-mods-10`) or `https://www.curseforge.com/minecraft/modpacks/<slug>` URL. Changing the modpack of an existing world is refused. |
| `CF_FILE_ID` | optional | A version's file ID (the number in `…/files/<id>`; the client file or its server pack). Unset: the newest release that has a server pack, checked at every start. |
| `JAVA_VERSION` | `auto` (default), `8`, `17`, `21`, `25` | `auto` picks Java from the pack's Minecraft version (below). |
| `MAX_PLAYERS`, `DIFFICULTY`, `GAME_MODE`, `MOTD` | optional | Written to `server.properties` when set; unset keeps the pack's own value. |
| `WHITELIST_ENABLED` | default `false` | Sets `white-list` and `enforce-whitelist`. |

The launcher always sets `online-mode=true`, `server-port=25565` and an empty
`server-ip`, and writes `eula=true` only after Wing's trusted Minecraft EULA
signal. Customer Java options and unknown `SQUAB_SYSTEM_*` variables are refused.
Java uses `-XX:MaxRAMPercentage=75.0`; the pack's own `user_jvm_args.txt` and
start scripts are ignored.

### Getting an API key

Sign in at <https://console.curseforge.com>, create an API key and paste it into
the server's `CF_API_KEY` field. The key is the owner's own: every request counts
against it and is subject to the
[CurseForge API terms](https://docs.curseforge.com/docs/legal/terms-of-use/).

## Java selection

| Minecraft | Java |
| --- | --- |
| up to 1.16.5 | 8 |
| 1.17 – 1.20.4 | 17 |
| 1.20.5 – 1.21.x | 21 |
| 26.1 and later | 25 |

## Installation flow

1. Resolve the project by ID or by slug (`/v1/mods/search?gameId=432&classId=4471&slug=…`).
   It must be a Minecraft modpack. `allowModDistribution=false` stops with a clear message.
2. Choose the version: `CF_FILE_ID`, or the newest approved *release* with a server
   pack (then beta, then alpha). A version without a server pack stops with a clear
   message. Squab never converts a client pack into a server.
3. Fetch the server pack's download location (`downloadUrl` or `/download-url`), accept
   only `https://` URLs on `edge.forgecdn.net`, `mediafilez.forgecdn.net` or
   `mediafiles.forgecdn.net`, stream at most the declared `fileLength` (≤ 2 GiB) and
   verify the API's SHA-1 and MD5. The zip is cached in `/data/.squab-curseforge/cache`.
4. Validate every entry before unpacking: no absolute, `..`, backslash or drive paths,
   no symlinks or special files, no encryption, at most 200,000 entries and 8 GiB
   unpacked (enforced while streaming), no entry compressed more than 200:1. A single
   top-level folder is stripped. Unpacking goes to a staging directory first.
5. Detect the loader and Minecraft version from, in order: the pack's `manifest.json`,
   `variables.txt` (ServerPackCreator), installer file names
   (`forge-<mc>-<v>-installer.jar`, `neoforge-<v>-installer.jar`), pre-installed
   `libraries/…/unix_args.txt`, and finally `manifest.json` inside the version's own
   client file. Start scripts are never executed or interpreted.
6. Install the loader with its **official** installer, not the copy in the pack:
   Forge from `maven.minecraftforge.net` and NeoForge from `maven.neoforged.net`
   (verified with the SHA-256 or SHA-1 the maven publishes), Fabric installer 1.1.2 and
   Quilt installer 0.15.1 pinned by size and SHA-256. For Fabric/Quilt the vanilla
   `server.jar` comes from Mojang's version manifest and is verified by SHA-1.
7. Start `java … @libraries/…/unix_args.txt nogui` (Forge 1.17+, NeoForge) or
   `java … -jar <launcher jar> nogui`.

Requests to `api.curseforge.com` carry the key in the `x-api-key` header and never
follow redirects. Downloads never carry it. HTTP 429 and 5xx are retried up to three
times, honouring `Retry-After` up to 120 seconds. An invalid key (401/403), unknown
project (404), missing server pack or blocked distribution exits with code 64 and a
plain message; integrity and download failures exit with 65. Nothing is changed in
`/data` until the server pack has been verified and fully validated.

## Updates

With `CF_FILE_ID` unset every start checks for a newer release; setting or changing
`CF_FILE_ID` while stopped pins, updates or rolls back the pack at the next start.
When the pinned version is installed, a start makes no API call. If CurseForge is
unreachable or rate limited while following the latest version, the installed
version starts and a warning is logged.

An update replaces pack files and keeps the server's state:

- the world (`level-name`, default `world`, plus `_nether`/`_the_end`), `server.properties`,
  `ops.json`, `whitelist.json`, `banned-*.json` and `usercache.json` are never
  overwritten; a world shipped by the pack is only installed when none exists;
- files the previous pack installed and the new one dropped are deleted when unchanged;
- pack files the owner modified are moved to `/data/.squab-curseforge/replaced/<time>/`
  before being replaced or removed (the three newest sets are kept);
- files the owner added (for example extra mods) are left alone;
- the new loader version is installed when it changed.

Take a backup before an update: mods can migrate worlds irreversibly, and an older
pack may not load an updated world.

## Readiness, stop and snapshots

Readiness is a Minecraft status ping on 25565/TCP with the maximum 900-second
deadline, because the first start downloads the pack and libraries and large packs
load slowly. If a very large pack misses it, start again: downloads and the
installation are cached in `/data`. Stop sends `stop` and allows 180 seconds.

Live snapshots use the vanilla console commands, which Forge, NeoForge, Fabric and
Quilt keep: `save-off`, `save-all flush`, `save-on`. The flush waits for `Saved the`,
because Minecraft 1.13 and later print `Saved the game` while 1.12.2 and older print
`Saved the world` (both verified in the boot checks). The cache, staging and
temporary directories, `logs` and `crash-reports` are excluded. Mods that keep data outside the world
save (for example external databases) are not paused by these commands; use a
stopped backup for those packs.

## Resources

The template requires at least 6 GiB memory, 20 GiB disk and 2 CPU cores. Modpack
authors commonly recommend 6–8 GiB; Java gets 75% of the limit as heap and the rest
covers metaspace and native memory, which are large for modded servers. Disk holds
the cached server pack, the unpacked pack, loader libraries, the world and update
backups. Choose more for large packs. Wing limits the container to 512 processes and
threads, enough for typical modded servers.

## Security notes

- The key is read from the secret file only, validated as printable ASCII, never
  printed, never written to `/data` and never in a process argument or the Java
  process environment. Backups do not contain it.
- Mods are code supplied by the modpack author and run as the same user as the
  launcher, so they could read the key file. Only run packs you trust; a key can be
  revoked and replaced in the CurseForge console and in Squab at any time.
- The root filesystem is read-only; Java's temporary directory and home are under
  `/data/.squab-curseforge`.

## Verification

`tests/test_curseforge.py` runs the launcher against `tests/curseforge_mock.py`, a
local double of the CurseForge API and CDN, and checks every error path plus that
the key is never logged and only sent to `api.curseforge.com`.
`python3 tools/boot-curseforge.py` boots a real server pack per Java line in the
image under Wing's container settings against the same double over HTTPS. See
[implementation/curseforge-image.md](../../implementation/curseforge-image.md).
