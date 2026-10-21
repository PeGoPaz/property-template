#!/usr/bin/env python3
"""
Writes AVIF and WebP next to every source JPEG in assets/.

The pages serve them through <picture>, newest format first, with the original
JPEG as the fallback. Paths follow one convention: photo.jpg -> photo.avif /
photo.webp, which is also how js/gallery.js finds them when it swaps images.

Needs cwebp (brew install webp) and swiftc for the AVIF encoder
(scripts/avif_encode.swift, which uses the system ImageIO).

Run after adding or replacing a photo:  python3 scripts/build_images.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'

AVIF_QUALITY = '0.7'
WEBP_QUALITY = '88'

# The header logo renders at 50px and is already tiny; not worth extra formats.
SKIP = {'logo.jpg'}


def build_avif_encoder(workdir: Path) -> Path:
    """Compile the Swift helper once, rather than interpreting it per image."""
    binary = workdir / 'avif_encode'
    result = subprocess.run(
        ['swiftc', '-O', '-o', str(binary), str(ROOT / 'scripts' / 'avif_encode.swift')],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f'swiftc failed:\n{result.stderr}')
    return binary


def newer(src: Path, out: Path) -> bool:
    return not out.exists() or src.stat().st_mtime > out.stat().st_mtime


def main() -> int:
    if not shutil.which('cwebp'):
        sys.exit('cwebp not found — install it with: brew install webp')
    if not shutil.which('swiftc'):
        sys.exit('swiftc not found — install the Xcode command line tools')

    sources = sorted(p for p in ASSETS.rglob('*.jpg') if p.name not in SKIP)
    if not sources:
        sys.exit(f'no JPEGs under {ASSETS}')

    with tempfile.TemporaryDirectory() as tmp:
        encoder = build_avif_encoder(Path(tmp))

        jpeg_total = avif_total = webp_total = 0
        built = skipped = 0

        for src in sources:
            avif, webp = src.with_suffix('.avif'), src.with_suffix('.webp')

            if newer(src, avif):
                subprocess.run([str(encoder), str(src), str(avif), AVIF_QUALITY], check=True)
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
