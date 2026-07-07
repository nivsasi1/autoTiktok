"""Reddit-post-style hook card: avatar + handle + title + engagement row,
rendered to a transparent PNG and overlaid on the video's opening seconds.
Sells the story like a screenshot instead of oversized subtitles."""

import os
import random

from PIL import Image, ImageDraw, ImageFont

CARD_W = 920
PAD = 44
AVATAR = 84
RADIUS = 36
TITLE_SIZE = 46
LINE_H = 60
INK = (26, 26, 27, 255)          # reddit's near-black
MUTED = (120, 124, 126, 255)
_FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def _font(name, size):
    return ImageFont.truetype(os.path.join(_FONT_DIR, name), size)


def _wrap(draw, text, font, width):
    lines, line = [], ""
    for word in text.split():
        cand = f"{line} {word}".strip()
        if line and draw.textlength(cand, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = cand
    if line:
        lines.append(line)
    return lines


def _paste_avatar(img, avatar_path, x, y):
    mask = Image.new("L", (AVATAR, AVATAR), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, AVATAR, AVATAR), fill=255)
    if avatar_path and os.path.exists(avatar_path):
        face = Image.open(avatar_path).convert("RGBA").resize((AVATAR, AVATAR))
    else:
        face = Image.new("RGBA", (AVATAR, AVATAR), (255, 69, 0, 255))  # reddit orange
        d = ImageDraw.Draw(face)
        d.text((AVATAR / 2, AVATAR / 2), "r/", font=_font("arialbd.ttf", 40),
               fill=(255, 255, 255, 255), anchor="mm")
    img.paste(face, (x, y), mask)


def make_card(title, handle, out_path, avatar_path=None, rng=None) -> str:
    """Render the card PNG; raises on missing fonts/Pillow issues — callers
    fall back to the plain text hook."""
    rng = random if rng is None else rng
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    title_font = _font("arialbd.ttf", TITLE_SIZE)
    name_font = _font("arialbd.ttf", 34)
    meta_font = _font("arial.ttf", 32)
    lines = _wrap(probe, title, title_font, CARD_W - 2 * PAD)[:6]

    head_h = AVATAR + 28
    body_h = len(lines) * LINE_H
    foot_h = 64
    h = PAD + head_h + body_h + foot_h + PAD
    img = Image.new("RGBA", (CARD_W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, CARD_W - 1, h - 1), RADIUS,
                        fill=(255, 255, 255, 247))

    _paste_avatar(img, avatar_path, PAD, PAD)
    nx = PAD + AVATAR + 24
    d.text((nx, PAD + 6), f"u/{handle}", font=name_font, fill=INK)
    d.text((nx, PAD + 48), f"{rng.randint(2, 11)}h ago", font=meta_font,
           fill=MUTED)

    ty = PAD + head_h
    for line in lines:
        d.text((PAD, ty), line, font=title_font, fill=INK)
        ty += LINE_H

    # engagement row: drawn shapes, no emoji-font roulette
    fy = ty + 18
    d.polygon([(PAD + 16, fy), (PAD + 32, fy + 22), (PAD, fy + 22)],
              fill=(255, 69, 0, 255))                       # upvote arrow
    ups = f"{rng.randint(18, 96) / 10:.1f}K"
    d.text((PAD + 44, fy - 4), ups, font=name_font, fill=INK)
    bx = PAD + 44 + int(probe.textlength(ups, font=name_font)) + 56
    d.ellipse((bx, fy - 2, bx + 30, fy + 24), outline=MUTED, width=4)
    d.text((bx + 44, fy - 4), f"{rng.randint(120, 980)}", font=name_font,
           fill=INK)

    img.save(out_path)
    return out_path
