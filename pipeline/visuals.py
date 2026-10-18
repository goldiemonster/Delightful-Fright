"""Background visuals for each line, in priority order:

1. A file you dropped in assets/ (image or video): your own art or public-domain paintings.
2. A free stock clip from Pexels (needs a free PEXELS_API_KEY).
3. A generated foggy night scene, so a render never fails.
"""
import os
import subprocess
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
W, H, FPS = 1080, 1920, 30
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}

# Desaturated, cold, grainy, vignetted: the look of the channel.
GRADE = (
    "eq=saturation=0.35:contrast=1.15:brightness=-0.05,"
    "colorbalance=bs=0.08:bm=0.04:rs=-0.05,"
    "noise=alls=10:allf=t,vignette=PI/4.5"
)


def find_local(spec: str) -> Path | None:
    for base in (ROOT, ROOT / "assets", ROOT / "assets" / "images"):
        p = base / spec
        if p.is_file() and p.suffix.lower() in VIDEO_EXT | IMAGE_EXT:
            return p
    return None


def fetch_pexels(query: str, cache: Path, used: set[int]) -> Path | None:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 15},
            headers={"Authorization": key},
            timeout=20,
        )
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! Pexels search failed for {query!r}: {e}")
        return None
    for video in r.json().get("videos", []):
        if video["id"] in used:
            continue
        files = [f for f in video["video_files"] if f.get("file_type") == "video/mp4" and f.get("height")]
        files = [f for f in files if f["height"] >= 1280] or files
        if not files:
            continue
        best = min(files, key=lambda f: f["height"])  # smallest file that's still HD
        dest = cache / f"pexels_{video['id']}.mp4"
        if not dest.exists():
            with requests.get(best["link"], stream=True, timeout=60) as dl:
                dl.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in dl.iter_content(1 << 16):
                        f.write(chunk)
        used.add(video["id"])
        return dest
    return None


def generate_scene(seed: int, dest: Path) -> Path:
    """A procedurally generated misty forest at night."""
    rng = np.random.default_rng(seed)
    w, h = W * 2, H * 2
    horizon = rng.uniform(0.5, 0.62)
    y = np.linspace(0, 1, h)[:, None]
    lift = np.exp(-(((y - horizon) / 0.18) ** 2))  # misty glow along the horizon
    sky = np.stack([14 + 80 * lift, 16 + 92 * lift, 26 + 110 * lift], -1)
    img = Image.fromarray(np.broadcast_to(sky, (h, w, 3)).astype(np.uint8))

    glow = Image.new("L", (w, h))
    gd = ImageDraw.Draw(glow)
    mx, my, r = rng.integers(w // 5, 4 * w // 5), rng.integers(h // 8, h // 3), rng.integers(110, 170)
    gd.ellipse([mx - r * 3, my - r * 3, mx + r * 3, my + r * 3], fill=70)  # halo
    gd.ellipse([mx - r, my - r, mx + r, my + r], fill=235)  # moon
    img = Image.composite(Image.new("RGB", (w, h), (205, 212, 225)), img, glow.filter(ImageFilter.GaussianBlur(40)))

    # Three rows of pine silhouettes, far (hazy) to near (black), with fog between them.
    for row, colour in ((0.0, (52, 60, 76)), (0.07, (26, 30, 40)), (0.16, (3, 4, 7))):
        trees = Image.new("L", (w, h))
        td = ImageDraw.Draw(trees)
        base = int(h * (horizon + row))
        for _ in range(rng.integers(10, 22)):
            x = rng.integers(-100, w + 100)
            tall = rng.integers(h // 10, h // 3) * (1 + row * 4)
            tw = rng.integers(40, 110) * (1 + row * 3)
            td.polygon([(x, base - tall), (x - tw, base + 40), (x + tw, base + 40)], fill=255)
        td.rectangle([0, base, w, h], fill=255)
        img = Image.composite(Image.new("RGB", (w, h), colour), img, trees.filter(ImageFilter.GaussianBlur(2)))

        fog = Image.new("L", (w, h))
        fd = ImageDraw.Draw(fog)
        for _ in range(12):
            fx, fy = rng.integers(-w // 3, w), base + rng.integers(-120, 120)
            fd.ellipse([fx, fy, fx + rng.integers(w // 2, w * 2), fy + rng.integers(60, 200)], fill=int(rng.integers(40, 90)))
        img = Image.composite(Image.new("RGB", (w, h), (110, 120, 138)), img, fog.filter(ImageFilter.GaussianBlur(70)))
    img.save(dest, quality=92)
    return dest


def resolve(spec: str, seed: int, cache: Path, used: set[int]) -> tuple[Path, str]:
    """Return (path, source label) for one line's visual."""
    if spec and (local := find_local(spec)):
        return local, "local"
    if spec and (clip := fetch_pexels(spec, cache, used)):
        return clip, "pexels"
    return generate_scene(seed, cache / f"scene_{seed}.jpg"), "generated"


def render_segment(src: Path, duration: float, dest: Path, zoom_in: bool = True):
    """Render one line's background as a 1080x1920 clip with a slow push-in."""
    frames = max(1, round(duration * FPS))
    fade = f"fade=t=in:st=0:d=0.25,fade=t=out:st={max(0.0, duration - 0.25):.3f}:d=0.25"
    if src.suffix.lower() in VIDEO_EXT:
        inputs = ["-stream_loop", "-1", "-i", str(src)]
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"setpts=1.3*PTS,fps={FPS},{GRADE},{fade}"  # slowed down for an eerie feel
        )
    else:
        z = f"1+0.12*on/{frames}" if zoom_in else f"1.12-0.12*on/{frames}"
        inputs = ["-i", str(src)]
        vf = (
            f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
            f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
            f"{GRADE},{fade}"
        )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", *inputs, "-t", f"{duration:.3f}",
        "-vf", vf + ",format=yuv420p", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-r", str(FPS), str(dest),
    ]
    subprocess.run(cmd, check=True)
