# Catalog artwork

Publisher artwork identifies games in the Squab creation catalog. Artwork and trademarks belong to their respective owners; inclusion does not imply endorsement. These presentation assets never enter game containers.

Every card is a 1280x640 (2:1) WebP that matches the Panel's catalog card: the publisher's key art fills the frame, a light uniform scrim is applied and the game's own logo is centred in the same box. [`compose.py`](compose.py) downloads the sources below, checks their SHA-256 and writes the cards:

```sh
uv run --with pillow --with cairosvg python artwork/compose.py
```

`template.json` names a card by its `main` URL. The release tooling pins every newly released manifest to the release tag instead (`https://raw.githubusercontent.com/squab-dev/squab-templates/vX.Y.Z/artwork/<card>.webp`), so a published manifest keeps showing the card it was released with even when the file on `main` changes later. Manifests published up to v0.2.7 keep their `main` URL; they are immutable and are not rewritten. Changing a card alone does not release; it reaches the catalog with the next release that writes a new manifest for that game. Keep cards that published manifests reference, because their URLs must stay valid.

Sources, downloaded 2026-10-06:

- paper.webp
  - art: PaperMC website in-game image, https://raw.githubusercontent.com/PaperMC/website/68f956e333ea03f3cba3bffd9e77daf083404e3a/src/assets/images/home-1.png
  - logo: PaperMC logo, https://raw.githubusercontent.com/PaperMC/website/68f956e333ea03f3cba3bffd9e77daf083404e3a/src/assets/brand/logo.svg
- hytale.webp
  - art: Hytale official desktop wallpaper (hytale.com/media), https://cdn.hytale.com/5e7a961e5e334000189a2a7a_1__1_.jpg
  - logo: https://hytale.com/images/logo.webp
- palworld.webp
  - art: Pocketpair Steam library hero, https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1623730/library_hero_2x.jpg
  - logo: Pocketpair Steam library logo, https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1623730/logo_2x.png
- curseforge.webp
  - background: generated in `compose.py`, a gradient in CurseForge's brand orange (no game or modpack imagery)
  - logo: the white CurseForge logo and wordmark, symbol `cf-logo-and-text` of the official CurseForge blog sprite, https://blog.curseforge.com/assets/img/sprite.svg

CurseForge is a mod platform rather than a game, so its card has no publisher key art. The logo is used unaltered (not recoloured, distorted or combined with other marks) to identify that the template installs modpacks from CurseForge. The card carries no Minecraft logo or imagery; the template name states that it runs Minecraft Java.

`palworld.jpg` is the earlier Steam store header (https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1623730/6912f19c43a95ff5fe514eedd35e68bf12335459/header.jpg, downloaded 2026-10-05). It stays only because published Palworld manifests up to v0.2.5 reference it; new revisions use `palworld.webp`.
