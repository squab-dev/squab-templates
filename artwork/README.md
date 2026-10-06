# Catalog artwork

Publisher artwork identifies games in the Squab creation catalog. Artwork and trademarks belong to their respective owners; inclusion does not imply endorsement. These presentation assets never enter game containers.

Every card is a 1280x640 (2:1) WebP that matches the Panel's catalog card: the publisher's key art fills the frame, a light uniform scrim is applied and the game's own logo is centred in the same box. [`compose.py`](compose.py) downloads the sources below, checks their SHA-256 and writes the cards:

```sh
uv run --with pillow --with cairosvg python artwork/compose.py
```

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

`palworld.jpg` is the earlier Steam store header (https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1623730/6912f19c43a95ff5fe514eedd35e68bf12335459/header.jpg, downloaded 2026-10-05). It stays only because published Palworld manifests up to v0.2.5 reference it; new revisions use `palworld.webp`.
