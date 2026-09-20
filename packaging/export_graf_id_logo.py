"""Export canonical transparent Graf-Id logo assets from graf-id-logo-source.png."""

from __future__ import annotations

import base64
import io
from collections import deque
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "packaging" / "graf-id-logo-source.png"
ASSETS = REPO / "desktop" / "src" / "assets"
PUBLIC = REPO / "desktop" / "public"
PADDING = 8
BACKGROUND_LUMA_MAX = 28


def is_background_pixel(red: int, green: int, blue: int) -> bool:
    peak = max(red, green, blue)
    if peak == 0:
        return True
    if peak > BACKGROUND_LUMA_MAX:
        return False
    # Keep green glow pixels; remove neutral near-black halo pixels.
    return green <= max(red, blue) + 4


def flood_remove_background(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    visited = [[False] * width for _ in range(height)]
    queue: deque[tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        if visited[y][x]:
            return
        red, green, blue, alpha = pixels[x, y]
        if alpha == 0 or not is_background_pixel(red, green, blue):
            return
        visited[y][x] = True
        pixels[x, y] = (0, 0, 0, 0)
        queue.append((x, y))

    for x in range(width):
        seed(x, 0)
        seed(x, height - 1)
    for y in range(height):
        seed(0, y)
        seed(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= width or ny >= height or visited[ny][nx]:
                continue
            red, green, blue, alpha = pixels[nx, ny]
            if alpha == 0 or not is_background_pixel(red, green, blue):
                continue
            visited[ny][nx] = True
            pixels[nx, ny] = (0, 0, 0, 0)
            queue.append((nx, ny))

    return rgba


def defringe_neutral_dark(image: Image.Image, peak_max: int = 8) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                continue
            peak = max(red, green, blue)
            if peak > peak_max:
                continue
            if abs(red - green) <= 2 and abs(green - blue) <= 2:
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def strip_favicon_glow(image: Image.Image, peak_cutoff: int) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                continue
            peak = max(red, green, blue)
            if peak <= peak_cutoff:
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def resize_favicon(image: Image.Image, size: int) -> Image.Image:
    resample = Image.Resampling.LANCZOS if size >= 128 else Image.Resampling.BOX
    resized = image.resize((size, size), resample)
    peak_max = 20 if size <= 48 else 8
    cleaned = defringe_neutral_dark(resized, peak_max=peak_max)
    if size <= 64:
        cutoff = 52 if size <= 24 else 50 if size <= 32 else 36
        cleaned = strip_favicon_glow(cleaned, cutoff)
    return cleaned


def write_favicon_png(image: Image.Image, size: int, path: Path) -> None:
    resize_favicon(image, size).save(path, format="PNG")


def write_favicon_ico(square: Image.Image, path: Path) -> None:
    sizes = (16, 24, 32, 48, 64, 128, 256)
    frames = [resize_favicon(square, size) for size in sizes]
    size_pairs = [(size, size) for size in sizes]
    # Pillow writes all sizes only when the largest image is the primary frame.
    frames[-1].save(
        path,
        format="ICO",
        sizes=size_pairs,
        append_images=frames[:-1],
    )


def write_public_favicons(square: Image.Image) -> None:
    favicon_master = resize_favicon(square, 128)
    write_svg(favicon_master, PUBLIC / "favicon.svg")
    write_favicon_png(square, 16, PUBLIC / "favicon-16x16.png")
    write_favicon_png(square, 32, PUBLIC / "favicon-32x32.png")
    resize_favicon(square, 180).save(PUBLIC / "apple-touch-icon.png", format="PNG")
    write_favicon_ico(square, PUBLIC / "favicon.ico")


def write_tauri_icons(square: Image.Image) -> None:
    icons_dir = REPO / "desktop" / "src-tauri" / "icons"
    write_favicon_png(square, 32, icons_dir / "32x32.png")
    write_favicon_png(square, 64, icons_dir / "64x64.png")
    write_favicon_png(square, 128, icons_dir / "128x128.png")
    write_favicon_png(square, 256, icons_dir / "128x128@2x.png")
    square.save(icons_dir / "icon.png", format="PNG")
    write_favicon_ico(square, icons_dir / "icon.ico")


def content_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    pixels = image.load()
    width, height = image.size
    min_x, min_y = width, height
    max_x, max_y = 0, 0
    for y in range(height):
        for x in range(width):
            _, _, _, alpha = pixels[x, y]
            if alpha == 0:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    return min_x, min_y, max_x, max_y


def crop_with_padding(image: Image.Image) -> Image.Image:
    min_x, min_y, max_x, max_y = content_bbox(image)
    left = max(min_x - PADDING, 0)
    top = max(min_y - PADDING, 0)
    right = min(max_x + PADDING + 1, image.width)
    bottom = min(max_y + PADDING + 1, image.height)
    return image.crop((left, top, right, bottom))


def png_to_data_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def write_svg(image: Image.Image, path: Path) -> None:
    width, height = image.size
    data_uri = png_to_data_uri(image)
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Graf-Id">\n'
        f'  <image width="{width}" height="{height}" href="{data_uri}" />\n'
        "</svg>\n"
    )
    path.write_text(svg, encoding="utf-8")


def pad_to_square(image: Image.Image) -> Image.Image:
    width, height = image.size
    size = max(width, height)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - width) // 2, (size - height) // 2)
    canvas.paste(image, offset)
    return canvas


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(
            f"Source icon missing: {SOURCE}\n"
            "Restore from git: git show HEAD:desktop/src-tauri/icons/icon.png > packaging/graf-id-logo-source.png"
        )

    ASSETS.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    source = Image.open(SOURCE)
    transparent = defringe_neutral_dark(flood_remove_background(source))
    cropped = crop_with_padding(transparent)
    square = pad_to_square(cropped)

    png_path = ASSETS / "graf-id-logo-transparent.png"
    cropped.save(png_path, format="PNG")
    cropped.save(PUBLIC / "graf-id-logo-transparent.png", format="PNG")

    write_public_favicons(square)
    write_tauri_icons(square)

    print(f"Wrote {png_path}")
    print("Updated desktop/public favicons and src-tauri/icons (transparent)")


if __name__ == "__main__":
    main()
