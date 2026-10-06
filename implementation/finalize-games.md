# Finalizing Paper, Hytale and Palworld (2026-10-06)

## Artwork

All cards are now 1280x640 WebP made by `artwork/compose.py` from pinned
official sources (key art plus the game's logo, same scrim and logo box):

| Card | Before | After |
| --- | --- | --- |
| Paper | 1920x1080 WebP, 16,214 bytes (PaperMC website illustration) | 1280x640 WebP, 43,672 bytes |
| Hytale | 600x347 transparent logo WebP, 54,878 bytes | 1280x640 WebP, 66,796 bytes |
| Palworld | 460x215 Steam header JPEG, 69,631 bytes | 1280x640 WebP, 82,514 bytes |

Paper and Hytale keep their URLs, so every published revision shows the new
cards. Palworld moves to `palworld.webp`; `palworld.jpg` stays for the published
v0.2.2 to v0.2.5 manifests. The cards were checked in a copy of the Panel's 2:1
`object-fit: cover` catalog card at 1280 px desktop and 390 px mobile widths.

## Images

Built with apko 1.4.6 and melange 0.61.2 from unchanged image inputs. The
release planner reports no image rebuild; the next release is metadata-only.

- `make check`: 51 tests and shell syntax checks passed.
- `make smoke` passed for Paper, Hytale and Palworld.
- Trivy 0.74.0 (`--severity HIGH,CRITICAL --ignore-unfixed`): 0 findings on all
  three images.
- Paper, `tools/boot-paper.py`: read-only, non-root container with the pinned
  build-129 JAR; the launcher updated to build 130, answered a status ping
  (Paper 26.2, protocol 776) and enforced `online-mode=true`. The template's
  snapshot steps were acknowledged (`Saved the game`, then automatic saving
  re-enabled); the copy taken while saving was off booted in a fresh volume
  with the original seed from `level.dat`. Console `stop` exited 0 both times.
- Hytale: account-free smoke reached the official device prompt
  (`https://oauth.accounts.hytale.com/oauth2/device/verify`, about 600 second
  expiry), health stayed failing, no UDP socket was open before sign-in, and
  `docker stop` exited 0.
- Palworld: healthy after about 8 seconds on an empty world; UDP 8211 bound on
  all addresses by UID 65532 and published; REST 8212 not published. Console
  `save` answered `World saved` in 0.09 seconds; console `stop` exited 0 in
  2.4 seconds without OOM.

## Snapshots

Paper keeps its live snapshot block. Hytale and Palworld do not declare
`live_snapshot`: Hytale has `world save --all` but no universe-wide save pause,
and Palworld has no autosave pause and its REST save cannot be awaited. Details
are in each runtime's README.

## Not verifiable here

- Hytale owner sign-in, authenticated download, world boot, readiness and
  update check on the released image.
- Real client joins for all three games through `play.squab.dev`, including
  UDP for Hytale (5520) and Palworld (8211). A protocol-level UDP reply was not
  obtained locally: Palworld's Unreal Engine 5.1 handshake needs the game's
  network version, and Hytale only opens its port after sign-in.
