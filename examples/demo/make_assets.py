"""Generate the demo's images and video clip (run from anywhere: uv run python examples/demo/make_assets.py)."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from narrate import media

HERE = Path(__file__).parent
W, H = 1920, 1080


def gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    t = np.linspace(0.0, 1.0, H)[:, None, None]
    rows = (1 - t) * np.array(top) + t * np.array(bottom)
    return Image.fromarray(np.repeat(rows, W, axis=1).astype(np.uint8), "RGB")


def landscape(name: str, sky_top, sky_bottom, sun, sun_y: int, hills) -> None:
    img = gradient(sky_top, sky_bottom)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((W * 0.62 - 260, sun_y - 260, W * 0.62 + 260, sun_y + 260), fill=sun + (90,))
    img.paste(glow.filter(ImageFilter.GaussianBlur(80)), (0, 0), glow.filter(ImageFilter.GaussianBlur(80)))
    draw = ImageDraw.Draw(img)
    draw.ellipse((W * 0.62 - 110, sun_y - 110, W * 0.62 + 110, sun_y + 110), fill=sun)
    for i, color in enumerate(hills):
        base = H * (0.62 + 0.11 * i)
        xs = np.linspace(0, W, 60)
        ys = base + 40 * np.sin(xs / (260 + 90 * i) + i * 1.7) + 25 * np.sin(xs / 97 + i)
        draw.polygon([(0, H)] + list(zip(xs.tolist(), ys.tolist())) + [(W, H)], fill=color)
    img.save(HERE / name, optimize=True)


landscape("sunrise.png", (40, 70, 140), (250, 180, 120), (255, 230, 160), 520,
          [(70, 90, 110), (45, 65, 80), (25, 40, 50)])
landscape("dusk.png", (20, 20, 60), (190, 90, 110), (255, 200, 150), 700,
          [(60, 40, 80), (40, 25, 55), (20, 12, 30)])
media.run(["-f", "lavfi", "-i", "life=size=320x180:mold=25:rate=30:ratio=0.08:death_color=#1b2a49:"
           "life_color=#ffd166:mold_color=#3a506b,scale=1280:720:flags=neighbor", "-t", "6",
           "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p",
           str(HERE / "life.mp4")])
print("wrote sunrise.png, dusk.png, life.mp4")
