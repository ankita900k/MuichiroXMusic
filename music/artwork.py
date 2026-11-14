"""Muichiro-branded dynamic music and welcome artwork."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "assets" / "muichiro"
MUSIC_TEMPLATE = ASSET_DIR / "music_template.png"
WELCOME_TEMPLATE = ASSET_DIR / "welcome_template.jpg"


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _fit(text: str, font, max_width: int) -> str:
    text = str(text or "")
    if not text:
        return "Unknown"
    while text and ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=font)[2] > max_width:
        text = text[:-2].rstrip() + "…"
    return text


def _duration(value):
    try:
        value = max(0, int(value or 0))
    except (TypeError, ValueError):
        value = 0
    return f"{value // 60}:{value % 60:02d}"


def _save_temp(image: Image.Image, suffix=".jpg") -> str:
    fd, path = tempfile.mkstemp(prefix="muichiro_art_", suffix=suffix)
    os.close(fd)
    image.save(path, "JPEG" if suffix == ".jpg" else "PNG", quality=94)
    return path


def make_music_card(title: str, artist: str, duration: int | None, thumbnail_path: str | None = None) -> str:
    base = Image.open(MUSIC_TEMPLATE).convert("RGBA")
    w, h = base.size
    draw = ImageDraw.Draw(base, "RGBA")

    # Place the actual track thumbnail inside the glowing Muichiro frame.
    frame = (84, 150, 672, 730)
    try:
        if thumbnail_path and os.path.isfile(thumbnail_path):
            cover = Image.open(thumbnail_path).convert("RGB")
        else:
            # Annie's published docs do not promise a thumbnail field; use Muichiro
            # character artwork as a branded fallback rather than leaving a black box.
            themed = Image.open(WELCOME_TEMPLATE).convert("RGB")
            cover = themed.crop((760, 0, 1280, 720))
        side = min(cover.size)
        left = (cover.width - side) // 2
        top = (cover.height - side) // 2
        cover = cover.crop((left, top, left + side, top + side)).resize(
            (frame[2] - frame[0], frame[3] - frame[1]), Image.Resampling.LANCZOS
        )
        mask = Image.new("L", cover.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, cover.width - 1, cover.height - 1), radius=55, fill=255)
        base.paste(cover, (frame[0], frame[1]), mask)
    except Exception:
        pass

    # Dynamic text area: no view-count field is ever rendered.
    title_font = _font(58, True)
    artist_font = _font(40)
    meta_font = _font(32)
    draw.text((710, 235), _fit(title, title_font, 870), font=title_font, fill=(245, 252, 255, 255), stroke_width=1, stroke_fill=(0, 30, 42, 255))
    draw.text((712, 340), _fit(f"Artist: {artist or 'Unknown Artist'}", artist_font, 850), font=artist_font, fill=(205, 231, 238, 255))
    draw.text((712, 420), f"Duration: {_duration(duration)}", font=meta_font, fill=(0, 238, 220, 255))
    draw.text((712, 500), "MUICHIRO  •  MIST MUSIC  •  VOICE CHAT", font=_font(23, True), fill=(0, 238, 220, 230))

    # Clear the template's sample progress line, then draw a neutral 0%-start line.
    draw.rectangle((700, 550, 1620, 735), fill=(3, 13, 21, 255))
    draw.rounded_rectangle((758, 600, 1595, 622), radius=11, fill=(95, 111, 120, 220))
    draw.rounded_rectangle((758, 600, 760, 622), radius=11, fill=(0, 239, 215, 255))
    draw.ellipse((746, 590, 772, 632), fill=(245, 255, 255, 255))
    draw.text((758, 640), "0:00", font=_font(31), fill=(210, 227, 233, 255))
    draw.text((1490, 640), _duration(duration), font=_font(31), fill=(210, 227, 233, 255))
    return _save_temp(base.convert("RGB"))


def make_welcome_card(name: str, username: str | None, user_id: int) -> str:
    base = Image.open(WELCOME_TEMPLATE).convert("RGBA")
    draw = ImageDraw.Draw(base, "RGBA")
    # Hide only the generated sample fields, preserving the original Muichiro artwork.
    draw.rounded_rectangle((68, 330, 760, 535), radius=24, fill=(2, 22, 35, 225), outline=(0, 225, 245, 220), width=3)
    label_font = _font(28, True)
    value_font = _font(28)
    fields = [
        ("Name", name or "Telegram User"),
        ("Username", f"@{username}" if username else "No username"),
        ("User ID", str(user_id)),
    ]
    y = 360
    for label, value in fields:
        draw.text((102, y), f"{label}:", font=label_font, fill=(0, 235, 240, 255))
        draw.text((300, y), _fit(value, value_font, 420), font=value_font, fill=(242, 250, 255, 255))
        y += 58
    return _save_temp(base.convert("RGB"))
