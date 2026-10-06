# CurseForge modpack image and template

Adds `images/curseforge`: one Wolfi image with OpenJDK 8.504, 17.0.20.1, 21.0.12.1
and 25.0.4.1 JREs, Python 3.14 and the `squab-curseforge-launcher`. The owner's
CurseForge API key is the sensitive field `CF_API_KEY` (specification 0.3.25,
D18). The template requires Core 0.15.0 and Wing 0.8.0 (protocol 1.9,
`config.secrets.v1`). Status: Early, until the operator tests it with their own key
and real players. Behaviour and configuration: [README](../images/curseforge/README.md).

The vendored template contract moves to specification 0.3.25 so the per-field
sensitive rules are validated here as Core will validate them (release tooling
change only; no image rebuild).

## Validation on 2026-10-06

- `make check` (with `requirements-dev.txt` installed): 71 tests pass, including
  20 CurseForge launcher tests and the release tests, which now derive the game
  list from `images/*/apko.yaml`.
- Local build with the pinned apko 1.4.6 / melange 0.61.2 using the same steps as
  `tools/build.sh` (see "Shared build tooling" below). `wolfi.lock.json` is the
  reviewed apko lock without the local launcher package.
- `make smoke GAME=curseforge`: UID 65532; all four `java -version`; exit 64 without
  the trusted EULA signal, without the key file, with the key in the environment and
  with `JAVA_TOOL_OPTIONS`; writable `/data` on a read-only root.
- Trivy 0.74.0: 0 HIGH/CRITICAL findings, fixable or not.
- Image: 1.36 GB uncompressed, 367 MB apko layer archive, about 362 MB gzip. The
  Java 8 JRE alone is 330 MB of that (17: 144 MB, 21: 167 MB, 25: 190 MB).

### Launcher tests against a CurseForge double

`tests/test_curseforge.py` runs the launcher against `tests/curseforge_mock.py`,
which follows the response shapes of the official REST API (`{"data": …}`, mod
`classId`/`allowModDistribution`, file `hashes` with algo 1 = SHA-1 and 2 = MD5,
`fileLength`, `downloadUrl`, `isServerPack`, `serverPackFileId`,
`parentProjectFileId`) and records every request's host and `x-api-key`. Covered:
project by slug, ID and URL; newest release with a server pack (a newer beta and a
newer release without server pack are skipped and logged); explicit file ID and a
restart with no API call; update keeping world, ops, owner-added mods and owner
`server.properties`, backing up an owner-edited config and deleting dropped files;
refused modpack change; loader detection from installer names, `variables.txt`,
NeoForge versions and the client manifest fallback; Java table and override;
missing key, key in env, wrong key path, malformed key, missing EULA signal,
customer Java options; 403 invalid key; 404 by ID and slug; non-modpack project;
no server pack (one version and whole project); `allowModDistribution=false` and a
file without a download location (403); 429 retried, then the installed version
starts, then a clear failure without an installation; SHA-1 mismatch and missing
SHA-1; zip-slip (`..`, absolute, backslash) and symlink entries; declared size over
2 GiB, a 1000:1 zip bomb, unpacked size limit and a body longer than declared.
After every test, all captured output and every file in `/data` are checked for the
key, and every request carrying it went to `api.curseforge.com`.

### Real boots (`python3 tools/boot-curseforge.py`)

An HTTPS double of `api.curseforge.com` and `edge.forgecdn.net` (throw-away CA)
served server packs built from official files: the loader from its official maven
or meta service and one real mod from Modrinth, verified by SHA-512. Loader
installers, libraries and Mojang jars came from the real internet. Containers ran
like Wing runs them: UID 65532, read-only root, all capabilities dropped,
`no-new-privileges`, 64 MiB exec `/tmp`, 6 GiB memory = swap, 2 CPUs, 512 PIDs, the
key as `/run/squab/secrets/CF_API_KEY` (0400, UID 65532, read-only mount) with only
`CF_API_KEY_FILE` in the environment. Each case: boot to a Minecraft status ping,
the template's snapshot commands with a copy of `/data` while saving was off,
console `stop` (exit 0), then a recreated container booting again from the same
volume.

| Java | Pack | Loader hint | First ready | Flush line | Second boot |
| --- | --- | --- | --- | --- | --- |
| 8 | Forge 1.12.2-14.23.5.2860 + JEI 4.22.0 | installer file name | 16 s | `Saved the world` | 8 s, no download |
| 17 | Forge 1.20.1-47.4.0 + JEI 15.62.0 | `variables.txt` | 50 s | `Saved the game` | 16 s, no download |
| 21 | NeoForge 21.1.256 (1.21.1) + JEI 19.57.0 | client manifest | 34 s | `Saved the game` | 14 s, no download |
| 25 | Fabric 0.19.5 (26.2) + Fabric API 0.161.0 | pack `manifest.json` | 16 s | `Saved the game` | 8 s, no download |

Ready times include download and loader installation. All four resumed autosave
(`Automatic saving is now enabled`; 1.12.2 `Turned on world auto-saving`), loaded
the mod and reported the configured MOTD and 10 slots. `server.properties` kept the
pack's `view-distance` and had `online-mode=true`. The Java process environment was
`HOME`, `LANG`, `PATH`, `TMPDIR` only. The key was absent from all container logs,
all process command lines and every file in the volume, and only
`api.curseforge.com` received it (24 API requests, 5 CDN downloads: four server
packs and one client manifest).

The first run showed that 1.12.2 prints `Saved the world`, so the flush step awaits
`Saved the` (matches 1.12.2 and 1.13+; `Saving the game` does not match).

## Findings outside this repository

- Wing's `minecraft_status` probe accepts any JSON object. Forge and NeoForge
  answer a status request during world preparation with a bare text object
  ("Server is still starting"), so Wing may report a modded server ready a few
  seconds before it accepts players. The boot harness requires a `version` field.
- Mods run as the launcher's user and can read the key file; the README tells
  owners to run only packs they trust.

## Shared build tooling

`tools/build.sh` and `tools/merge-lock.py` enumerate the allowed images and
launchers, so CI's `make build GAME=curseforge` cannot build this image without
changing them. That change is not part of this branch; it re-versions Paper,
Hytale and Palworld at the next release because those files are shared build
inputs. Until it lands, the image verify job for `curseforge` fails at its build
step. Not verified here: a real CurseForge key, a real CurseForge modpack, a real
client joining.
