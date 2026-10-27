#!/usr/bin/env python3
"""
Writes AVIF and WebP next to every source JPEG in assets/.

The pages serve them through <picture>, newest format first, with the original
JPEG as the fallback. Paths follow one convention: photo.jpg -> photo.avif /
photo.webp, which is also how js/gallery.js finds them when it swaps images.

Needs avifenc and cwebp: brew install libavif webp

AVIF comes from libavif's avifenc rather than macOS's own encoder. ImageIO
splits any photo wider than about 1000 px into a grid of 512 px tiles, which
Firefox (159) cannot display at all, and Chrome rendered its odd-sized output
as a blank image. avifenc writes each photo as one image, at its own size.

Run after adding or replacing a photo:  python3 scripts/build_images.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'

AVIF_QUALITY = '65'   # avifenc's 0-100 scale
WEBP_QUALITY = '88'

# The header logo renders at 50px and is already tiny; not worth extra formats.
SKIP = {'logo.jpg'}


def newer(src: Path, out: Path) -> bool:
    return not out.exists() or src.stat().st_mtime > out.stat().st_mtime


def main() -> int:
    for tool, package in (('avifenc', 'libavif'), ('cwebp', 'webp')):
        if not shutil.which(tool):
            sys.exit(f'{tool} not found — install it with: brew install {package}')

    sources = sorted(p for p in ASSETS.rglob('*.jpg') if p.name not in SKIP)
    if not sources:
        sys.exit(f'no JPEGs under {ASSETS}')

    jpeg_total = avif_total = webp_total = 0
    built = skipped = 0

    for src in sources:
        avif, webp = src.with_suffix('.avif'), src.with_suffix('.webp')

        if newer(src, avif):
            subprocess.run(
                ['avifenc', '-q', AVIF_QUALITY, '-s', '6', '-j', 'all', str(src), str(avif)],
                check=True, stdout=subprocess.DEVNULL,
            )
            built += 1
        else:
            skipped += 1

        if newer(src, webp):
            subprocess.run(
                ['cwebp', '-quiet', '-q', WEBP_QUALITY, str(src), '-o', str(webp)],
                check=True,
            )

        jpeg_total += src.stat().st_size
        avif_total += avif.stat().st_size
        webp_total += webp.stat().st_size

    mb = lambda n: n / 1024 / 1024
    pct = lambda n: round(n * 100 / jpeg_total)
    print(f'{len(sources)} images ({built} rebuilt, {skipped} up to date)')
    print(f'  JPEG {mb(jpeg_total):5.1f} MB')
    print(f'  WebP {mb(webp_total):5.1f} MB  ({pct(webp_total)}%)')
    print(f'  AVIF {mb(avif_total):5.1f} MB  ({pct(avif_total)}%)')

    return 0


if __name__ == '__main__':
    sys.exit(main())
