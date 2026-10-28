#!/usr/bin/env python3
"""
Writes AVIF and WebP next to every source JPEG in assets/, at its own size and
at each of build.VARIANT_WIDTHS narrower than it.

The pages serve them through <picture>, newest format first, with the original
JPEG as the fallback, and a srcset lets the browser pick the narrowest file
that still fills the space on its screen: a phone does not need the 1920 px
hero. Paths follow one convention: photo.jpg -> photo.avif / photo.webp, and
photo-640.avif / photo-640.webp for the narrower copies.

Needs avifenc and cwebp/dwebp: brew install libavif webp

AVIF comes from libavif's avifenc rather than macOS's own encoder. ImageIO
splits any photo wider than about 1000 px into a grid of 512 px tiles, which
Firefox (159) cannot display at all, and Chrome rendered its odd-sized output
as a blank image. avifenc writes each photo as one image, at its own size.
avifenc cannot resize, so a narrower copy is first scaled by cwebp, losslessly,
and handed to it as PNG.

Run after adding or replacing a photo:  python3 scripts/build_images.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from build import VARIANT_WIDTHS, jpeg_size, variant_path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'

AVIF_QUALITY = '65'   # avifenc's 0-100 scale
WEBP_QUALITY = '88'

# The header logo renders at 50px and is already tiny; not worth extra formats.
SKIP = {'logo.jpg'}


def newer(src: Path, out: Path) -> bool:
    return not out.exists() or src.stat().st_mtime > out.stat().st_mtime


def run(*args: str) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def encode(src: Path, avif: Path, webp: Path) -> None:
    run('avifenc', '-q', AVIF_QUALITY, '-s', '6', '-j', 'all', str(src), str(avif))
    run('cwebp', '-quiet', '-q', WEBP_QUALITY, str(src), '-o', str(webp))


def encode_narrower(src: Path, width: int, avif: Path, webp: Path, tmp: Path) -> None:
    run('cwebp', '-quiet', '-q', WEBP_QUALITY, '-resize', str(width), '0', str(src), '-o', str(webp))
    # The AVIF starts from a lossless resize, not from that WebP, so it is
    # compressed once rather than twice.
    scaled = tmp / 'scaled.webp'
    png = tmp / 'scaled.png'
    run('cwebp', '-quiet', '-lossless', '-exact', '-resize', str(width), '0', str(src), '-o', str(scaled))
    run('dwebp', '-quiet', str(scaled), '-o', str(png))
    run('avifenc', '-q', AVIF_QUALITY, '-s', '6', '-j', 'all', str(png), str(avif))


def main() -> int:
    for tool, package in (('avifenc', 'libavif'), ('cwebp', 'webp'), ('dwebp', 'webp')):
        if not shutil.which(tool):
            sys.exit(f'{tool} not found — install it with: brew install {package}')

    sources = sorted(p for p in ASSETS.rglob('*.jpg') if p.name not in SKIP)
    if not sources:
        sys.exit(f'no JPEGs under {ASSETS}')

    jpeg_total = avif_total = webp_total = 0
    built = skipped = 0

    with tempfile.TemporaryDirectory() as tmp:
        for src in sources:
            width = jpeg_size(src)[0]
            outputs = [(None, src.with_suffix('.avif'), src.with_suffix('.webp'))]
            outputs += [(w, variant_path(src, w, '.avif'), variant_path(src, w, '.webp'))
                        for w in VARIANT_WIDTHS if w < width]

            for w, avif, webp in outputs:
                if newer(src, avif) or newer(src, webp):
                    if w is None:
                        encode(src, avif, webp)
                    else:
                        encode_narrower(src, w, avif, webp, Path(tmp))
                    built += 1
                else:
                    skipped += 1

            # Totals compare the full-size files, as before.
            jpeg_total += src.stat().st_size
            avif_total += outputs[0][1].stat().st_size
            webp_total += outputs[0][2].stat().st_size

    mb = lambda n: n / 1024 / 1024
    pct = lambda n: round(n * 100 / jpeg_total)
    print(f'{len(sources)} images, {built + skipped} sizes ({built} rebuilt, {skipped} up to date)')
    print(f'  JPEG {mb(jpeg_total):5.1f} MB')
    print(f'  WebP {mb(webp_total):5.1f} MB  ({pct(webp_total)}%)')
    print(f'  AVIF {mb(avif_total):5.1f} MB  ({pct(avif_total)}%)')

    return 0


if __name__ == '__main__':
    sys.exit(main())
