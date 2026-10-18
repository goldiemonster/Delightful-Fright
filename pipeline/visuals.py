"""Background visuals for each line, in priority order:

1. A file you dropped in assets/ (image or video): your own art or public-domain paintings.
2. An AI-generated still from the line's shot prompt (free, no key needed:
   Pollinations FLUX; or Hugging Face FLUX.1-schnell when HF_TOKEN is set).
3. A free stock clip from Pexels for the line's `visual` search (needs PEXELS_API_KEY).
4. A generated foggy night scene, so a render never crashes. It shows nothing
   from the story, so QA fails any video that uses it.

Stills get smooth, sub-pixel camera moves (push-ins, pans, handheld drift)
rendered frame by frame, then the channel's colour grade, grain and vignette.
"""
import hashlib
import io
import os
import subprocess
import time
import urllib.parse
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
W, H, FPS = 1080, 1920, 30
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}

# Low-key and warm, like a room lit by one lamp (the channel's look); or cold, or sickly.
GRADES = {
    # Muted amber highlights over blue-grey shadows: the channel's ashcan-noir look.
    "noir": (
        "eq=contrast=1.15:brightness=-0.04:saturation=0.55:gamma=0.92,"
        "colorbalance=rs=-0.04:gs=0.0:bs=0.06:rm=0.02:bm=-0.01:rh=0.08:gh=0.03:bh=-0.07"
    ),
    "amber": (
        "eq=contrast=1.18:brightness=-0.05:saturation=0.82:gamma=0.9,"
        "colorbalance=rs=0.07:gs=0.01:bs=-0.08:rm=0.05:bm=-0.05:rh=0.03:bh=-0.06"
    ),
    "cold": "eq=contrast=1.15:brightness=-0.05:saturation=0.35,colorbalance=bs=0.08:bm=0.04:rs=-0.05",
    "green": "eq=contrast=1.2:brightness=-0.06:saturation=0.6,colorbalance=gs=0.06:gm=0.05:rs=-0.04:bh=-0.04",
}
FINISH = "noise=alls=8:allf=t+u,vignette=PI/4.2"

DEFAULT_STYLE = (
    "mature charcoal and graphite ashcan noir illustration, realistic adult anatomy, "
    "legible faces and clues, heavy cross-hatched shadows, muted amber and blue-grey palette, "
    "vertical 9:16 single frame, no collage, no text, no watermark"
)

MOVES = ["push_in", "drift_left", "pull_out", "rise", "push_in", "drift_right", "sink"]


def find_local(spec: str) -> Path | None:
    for base in (ROOT, ROOT / "assets", ROOT / "assets" / "images"):
        p = base / spec
        if p.is_file() and p.suffix.lower() in VIDEO_EXT | IMAGE_EXT:
            return p
    return None


def _valid_image(data: bytes) -> bool:
    try:
        im = Image.open(io.BytesIO(data))
        im.verify()
        return min(im.size) >= 512
    except Exception:
        return False


def _huggingface(prompt: str, seed: int) -> bytes | None:
    token = os.environ.get("HF_TOKEN")
    if not token:
        return None
    r = requests.post(
        "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell",
        headers={"Authorization": f"Bearer {token}"},
        json={"inputs": prompt, "parameters": {"width": 768, "height": 1344, "seed": seed}},
        timeout=180,
    )
    r.raise_for_status()
    return r.content


def _pollinations(prompt: str, seed: int) -> bytes | None:
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
    params = {"width": 1080, "height": 1920, "seed": seed, "model": "flux", "nologo": "true"}
    headers = {}
    if token := os.environ.get("POLLINATIONS_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(url, params=params, headers=headers, timeout=180)
    r.raise_for_status()
    return r.content


_unreachable: set = set()
PLACEHOLDER = "placeholder"  # the generated fog scene: not a story shot


def fetch_ai_image(prompt: str, style: str, seed: int, cache: Path) -> Path | None:
    full = f"{style}. {prompt}"
    dest = cache / f"ai_{hashlib.sha1(f'{full}|{seed}'.encode()).hexdigest()[:16]}.jpg"
    if dest.exists():
        return dest
    for source in (_huggingface, _pollinations):
        for attempt in range(4):
            if source in _unreachable:
                break
            try:
                data = source(full, seed)
            except requests.ConnectionError as e:
                print(f"  ! can't reach {source.__name__.strip('_')}, skipping it: {type(e).__name__}")
                _unreachable.add(source)
                break
            except requests.RequestException as e:
                print(f"  ! {source.__name__.strip('_')} attempt {attempt + 1} failed: {e}")
                time.sleep(8 * (attempt + 1))
                continue
            if data is None:
                break
            if _valid_image(data):
                Image.open(io.BytesIO(data)).convert("RGB").save(dest, quality=95)
                return dest
            time.sleep(4)
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


def shot_prompt(line: dict, anchors: dict | str) -> str:
    """Build a shot prompt the way the production bible does: anchors, camera, action, evidence.

    Anchors keep cast and places consistent. A named anchor (narrator, grandmother...)
    is described inline only in shots that mention it, so the model draws who the
    shot is about and nobody else; the `world` anchor goes into every shot.
    """
    scene = line.get("scene", "")
    if not scene:
        return ""
    parts = [scene]
    if line.get("action"):
        parts.append(f"single physical action: {line['action']}")
    if line.get("evidence"):
        parts.append(f"clearly visible: {line['evidence']}")
    if line.get("camera"):
        parts.append(f"camera: {line['camera']}")
    text = ", ".join(parts)
    if isinstance(anchors, str):
        return f"{text}, continuity: {anchors}" if anchors else text
    for name, desc in anchors.items():
        if name != "world" and name.lower() in text.lower():
            i = text.lower().index(name.lower()) + len(name)
            i += 2 if text[i:i + 2] == "'s" else 0
            text = f"{text[:i]} ({desc}){text[i:]}"
    if anchors.get("world"):
        text += f", setting: {anchors['world']}"
    return text


def resolve(line: dict, style: str, seed: int, cache: Path, used: set[int], anchors: dict | str = "") -> tuple[Path, str]:
    """Return (path, source label) for one line's visual."""
    spec, scene = line.get("visual", ""), shot_prompt(line, anchors)
    if spec and (local := find_local(spec)):
        return local, "local"
    if scene and (still := fetch_ai_image(scene, style, seed, cache)):
        return still, "ai"
    if spec and (clip := fetch_pexels(spec, cache, used)):
        return clip, "pexels"
    if line.get("scene") and (clip := fetch_pexels(line["scene"], cache, used)):
        return clip, "pexels"
    # Last resort, so a render never crashes; QA fails the video if any shot ends up here.
    return generate_scene(seed, cache / f"scene_{seed}.jpg"), PLACEHOLDER


def _still_frames(src: Path, duration: float, move: str, shake: bool, seed: int):
    """Yield raw RGB frames of a slow camera move over a still image."""
    frames = max(1, round(duration * FPS))
    img = Image.open(src).convert("RGB")
    # Cover the frame with 16% headroom so the camera can move without showing edges.
    scale = max(W / img.width, H / img.height) * 1.16
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    iw, ih = img.size
    rng = np.random.default_rng(seed)
    phase = rng.uniform(0, 100, 4)
    for f in range(frames):
        p = f / max(1, frames - 1)
        ease = p * p * (3 - 2 * p)  # smoothstep
        zoom = {"push_in": 1 + 0.10 * ease, "pull_out": 1.10 - 0.10 * ease}.get(move, 1.05)
        cw = min(iw, ih * W / H) / 1.16 / zoom  # visible width in source pixels
        ch = cw * H / W
        cx, cy = iw / 2, ih / 2
        slack_x, slack_y = (iw - cw) / 2, (ih - ch) / 2
        if move == "drift_left":
            cx += slack_x * 0.8 * (0.5 - ease)
        elif move == "drift_right":
            cx -= slack_x * 0.8 * (0.5 - ease)
        elif move == "rise":
            cy += slack_y * 0.8 * (0.5 - ease)
        elif move == "sink":
            cy -= slack_y * 0.8 * (0.5 - ease)
        # Handheld drift: two slow sines per axis, a few pixels; a hard shake on impacts.
        t = f / FPS
        amp = 3.0 + (14.0 * np.exp(-t * 5) if shake else 0.0)
        hz = 1.0 if not shake else 1.0 + 6 * np.exp(-t * 4)
        cx += amp * (np.sin(0.7 * hz * t + phase[0]) + 0.5 * np.sin(1.9 * hz * t + phase[1]))
        cy += amp * (np.sin(0.6 * hz * t + phase[2]) + 0.5 * np.sin(1.7 * hz * t + phase[3]))
        cx = min(max(cx, cw / 2), iw - cw / 2)
        cy = min(max(cy, ch / 2), ih - ch / 2)
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        yield img.transform((W, H), Image.EXTENT, box, Image.BICUBIC).tobytes()


def render_segment(src: Path, duration: float, dest: Path, grade: str = "noir", move: str = "push_in",
                   impact: bool = False, seed: int = 0):
    """Render one line's background as a 1080x1920 clip."""
    look = f"{GRADES.get(grade, GRADES['noir'])},{FINISH}"
    if impact:  # a white flash that decays as the boom hits
        look += ",eq=brightness='if(lt(t,0.18),0.55*(1-t/0.18),0)':eval=frame"
    out = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
           "-r", str(FPS), "-t", f"{duration:.3f}", str(dest)]
    if src.suffix.lower() in VIDEO_EXT:
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"setpts=1.3*PTS,fps={FPS},{look}"  # slowed down for an eerie feel
        )
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(src), "-vf", vf, *out]
        subprocess.run(cmd, check=True)
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-vf", look, *out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for frame in _still_frames(src, duration, move, impact, seed):
        proc.stdin.write(frame)
    proc.stdin.close()
    if proc.wait():
        raise subprocess.CalledProcessError(proc.returncode, cmd)
