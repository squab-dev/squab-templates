"""Compose the catalog cards from official publisher assets.

Every card is 1280x640 WebP: the publisher's key art fills the frame and the
game's own logo is centred in the same box with the same scrim and shadow.
Sources are pinned by SHA-256; a changed upstream file stops the build.

    uv run --with pillow --with cairosvg python artwork/compose.py
"""
import hashlib
import io
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SIZE = (1280, 640)
LOGO_BOX = (680, 370)
QUALITY = 82
OUT = Path(__file__).resolve().parent

CARDS = {
    'paper': {
        'art': ('https://raw.githubusercontent.com/PaperMC/website/68f956e333ea03f3cba3bffd9e77daf083404e3a/src/assets/images/home-1.png',
                '4776a74dff039e3348327973ebaaac95024c95f35c56d2f26dee718a383ef6a1'),
        'logo': ('https://raw.githubusercontent.com/PaperMC/website/68f956e333ea03f3cba3bffd9e77daf083404e3a/src/assets/brand/logo.svg',
                 'e0cd4fec7abaaaf02e559ab906acdd11fc813d31e9cfea98a6cff25b9c7eddcf'),
        'focus': (0.5, 0.45),
    },
    'hytale': {
        'art': ('https://cdn.hytale.com/5e7a961e5e334000189a2a7a_1__1_.jpg',
                'e9457f6e3987c4541055a045b4bdd76ff22ecfd38ea3191a8ff060d366cc8080'),
        'logo': ('https://hytale.com/images/logo.webp',
                 'ec0317a03669e9798a41beb04a197f411bfbfd2b5b18d7e40dbf83e56dc12663'),
        'focus': (0.5, 0.5),
    },
    'palworld': {
        'art': ('https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1623730/library_hero_2x.jpg',
                '79d7d684f02a5fe9dce40bea3f3e69ad227ed84b31531ab85c6563eec9fc24aa'),
        'logo': ('https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/1623730/logo_2x.png',
                 '058014c76c02f9e0fbde4f2567402d0d05b20908875e0d9a2a3d79a44c0ccb6d'),
        'focus': (0.5, 0.5),
    },
}


def fetch(url, sha256):
    request = urllib.request.Request(url, headers={'User-Agent': 'squab-templates-artwork'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha256:
        sys.exit(f'{url}: expected SHA-256 {sha256}, got {actual}')
    return data


def load(url, data):
    if url.endswith('.svg'):
        import cairosvg
        data = cairosvg.svg2png(bytestring=data, output_width=LOGO_BOX[1] * 2)
    return Image.open(io.BytesIO(data))


def cover(image, focus):
    """Crop to 2:1 around the focal point, then scale to the card size."""
    image = image.convert('RGB')
    ratio = SIZE[0] / SIZE[1]
    width, height = image.size
    crop_w, crop_h = (width, round(width / ratio)) if width / height < ratio else (round(height * ratio), height)
    left = min(max(round(width * focus[0] - crop_w / 2), 0), width - crop_w)
    top = min(max(round(height * focus[1] - crop_h / 2), 0), height - crop_h)
    return image.crop((left, top, left + crop_w, top + crop_h)).resize(SIZE, Image.LANCZOS)


def compose(art, logo, focus):
    card = cover(art, focus).convert('RGBA')
    # Same scrim on every card: a light overall dim plus a soft oval behind the logo.
    card = Image.alpha_composite(card, Image.new('RGBA', SIZE, (0, 0, 0, 64)))
    oval = Image.new('L', SIZE, 0)
    w, h = LOGO_BOX
    cx, cy = SIZE[0] // 2, SIZE[1] // 2
    ImageDraw.Draw(oval).ellipse((cx - w * 0.75, cy - h * 0.75, cx + w * 0.75, cy + h * 0.75), fill=110)
    oval = oval.filter(ImageFilter.GaussianBlur(90))
    card = Image.composite(Image.new('RGBA', SIZE, (0, 0, 0, 255)), card, oval)

    logo = logo.convert('RGBA')
    bbox = logo.getchannel('A').getbbox()
    logo = logo.crop(bbox)
    scale = min(w / logo.width, h / logo.height)
    logo = logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.LANCZOS)
    x, y = cx - logo.width // 2, cy - logo.height // 2
    shadow = Image.new('RGBA', SIZE, (0, 0, 0, 0))
    alpha = Image.new('L', SIZE, 0)
    alpha.paste(logo.getchannel('A'), (x, y + 6))
    alpha = ImageChops.multiply(alpha.filter(ImageFilter.GaussianBlur(14)), Image.new('L', SIZE, 150))
    shadow.putalpha(alpha)
    card = Image.alpha_composite(card, shadow)
    card.alpha_composite(logo, (x, y))
    return card.convert('RGB')


def main(names):
    for name in names or CARDS:
        spec = CARDS[name]
        art = load(spec['art'][0], fetch(*spec['art']))
        logo = load(spec['logo'][0], fetch(*spec['logo']))
        path = OUT / f'{name}.webp'
        compose(art, logo, spec['focus']).save(path, 'WEBP', quality=QUALITY, method=6)
        print(f'{path.name}: {SIZE[0]}x{SIZE[1]}, {path.stat().st_size} bytes')


if __name__ == '__main__':
    main(sys.argv[1:])
