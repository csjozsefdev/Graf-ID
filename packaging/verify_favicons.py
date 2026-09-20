"""Verify Graf-Id favicons have transparent backgrounds (alpha), not baked black."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "packaging" / "graf-id-logo-source.png"
PUBLIC = REPO / "desktop" / "public"
TAURI_ICO = REPO / "desktop" / "src-tauri" / "icons" / "icon.ico"

PNG_TARGETS = (
    PUBLIC / "favicon-16x16.png",
    PUBLIC / "favicon-32x32.png",
    PUBLIC / "apple-touch-icon.png",
)
ICO_TARGETS = (
    PUBLIC / "favicon.ico",
    TAURI_ICO,
)


def ico_image_count(path: Path) -> int:
    data = path.read_bytes()
    return struct.unpack("<HHH", data[:6])[2]


def assert_png_transparent(path: Path) -> None:
    image = Image.open(path).convert("RGBA")
    corner = image.getpixel((0, 0))
    if corner[3] != 0:
        raise AssertionError(f"{path}: corner not transparent: {corner}")
    black_opaque = sum(
        1
        for red, green, blue, alpha in image.get_flattened_data()
        if alpha > 0 and red == 0 and green == 0 and blue == 0
    )
    if black_opaque > 0:
        raise AssertionError(f"{path}: {black_opaque} opaque black pixels remain")


def assert_ico_transparent(path: Path, min_entries: int = 4) -> None:
    count = ico_image_count(path)
    if count < min_entries:
        raise AssertionError(f"{path}: expected >= {min_entries} ICO sizes, got {count}")
    icon = Image.open(path)
    for index in range(getcount(icon)):
        icon.seek(index)
        frame = icon.convert("RGBA")
        if frame.getpixel((0, 0))[3] != 0:
            raise AssertionError(f"{path} frame {index}: corner not transparent")


def getcount(icon: Image.Image) -> int:
    try:
        while True:
            icon.seek(icon.tell() + 1)
    except EOFError:
        return icon.tell() + 1


def main() -> int:
    if not SOURCE.is_file():
        print(f"Missing source: {SOURCE}", file=sys.stderr)
        return 1

    for target in PNG_TARGETS:
        if not target.is_file():
            print(f"Missing favicon: {target}", file=sys.stderr)
            return 1
        assert_png_transparent(target)

    for target in ICO_TARGETS:
        if not target.is_file():
            print(f"Missing ICO: {target}", file=sys.stderr)
            return 1
        assert_ico_transparent(target)

    print("Favicon transparency OK")
    print(f"  source: {SOURCE}")
    for target in PNG_TARGETS:
        print(f"  png: {target.relative_to(REPO)}")
    for target in ICO_TARGETS:
        print(f"  ico: {target.relative_to(REPO)} ({ico_image_count(target)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
