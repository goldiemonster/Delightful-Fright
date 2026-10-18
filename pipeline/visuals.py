"""Background visuals for each line, in priority order:

1. A file you dropped in assets/ (image or video): your own art or public-domain paintings.
2. A master plate (`plate:` on the line): one painting per room or character, painted once
   and reused for every shot set there, optionally reframed (`frame:`) or edited from another
   plate (a hand on the door, the wardrobe now open). This is what keeps faces, rooms and props
   identical from shot to shot.
3. An AI-generated still from the line's own shot prompt.
4. A free stock clip from Pexels for the line's `visual` search (needs PEXELS_API_KEY).
5. A generated foggy night scene, so a render never crashes. It shows nothing
   from the story, so QA fails any video that uses it.

Paintings come from Hugging Face FLUX.1-schnell (HF_TOKEN), Pollinations FLUX (POLLINATIONS_TOKEN;
its free tier stamps a watermark, so it is skipped without a token) or the free AI Horde cluster.

Stills get smooth, sub-pixel camera moves (push-ins, pans, handheld drift)
rendered frame by frame, then the channel's colour grade, grain and vignette.
"""
import base64
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
    # The channel's look: low key, warm lamp-lit highlights, cool near-black shadows, colour kept.
    "channel": (
        "eq=contrast=1.08:brightness=-0.03:saturation=0.92:gamma=0.94,"
        "colorbalance=rs=-0.03:gs=0.0:bs=0.04:rm=0.03:bm=-0.03:rh=0.06:gh=0.02:bh=-0.06"
    ),
    # Muted amber highlights over blue-grey shadows, closer to black and white.
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
FINISH = "noise=alls=6:allf=t+u,vignette=PI/4.5"

# The channel's art direction: gritty, detailed, painterly realism lit by practical lamps.
DEFAULT_STYLE = (
    "Warm-toned gritty cinematic digital painting, dark graphic novel realism, richly detailed textured brushwork, "
    "ordinary adults in worn everyday clothes, warm amber practical light against deep blue-black shadows, "
    "grime and damp reflective surfaces, low-key lighting, quiet unsettling mood, single frame, "
    "no text, no watermark"
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
    token = os.environ.get("POLLINATIONS_TOKEN")
    if not token:  # the free tier stamps "pollinations.ai" on the image
        return None
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
    params = {"width": 1080, "height": 1920, "seed": seed, "model": "flux", "nologo": "true"}
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, params=params, headers=headers, timeout=180)
    r.raise_for_status()
    return r.content


def _aihorde(prompt: str, seed: int, size: tuple[int, int] = (576, 1024), source: Path | None = None,
             strength: float = 0.55) -> bytes | None:
    """AI Horde (aihorde.net): free volunteer GPUs. Slow for anonymous users, but it never runs out.
    With `source`, it repaints that image (img2img) so an edit keeps the original's room and light."""
    api, key = "https://aihorde.net/api/v2", os.environ.get("AIHORDE_API_KEY", "0000000000")
    headers = {"apikey": key, "Client-Agent": "delightful-fright:1:github"}
    params = {"sampler_name": "k_euler", "cfg_scale": 1, "steps": 8, "width": size[0], "height": size[1],
              "seed": str(seed), "n": 1}
    body = {"prompt": prompt + " ### text, watermark, signature, logo, cartoon, anime, blurry, deformed hands, "
                               "extra fingers", "params": params,
            "models": ["Flux.1-Schnell fp8 (Compact)"], "r2": True, "nsfw": False, "censor_nsfw": True}
    if source is not None:
        buf = io.BytesIO()
        Image.open(source).convert("RGB").resize(size, Image.LANCZOS).save(buf, "WEBP", quality=92)
        body.update(source_image=base64.b64encode(buf.getvalue()).decode(), source_processing="img2img")
        params["denoising_strength"] = strength
    r = requests.post(f"{api}/generate/async", json=body, headers=headers, timeout=60)
    r.raise_for_status()
    job = r.json()["id"]
    deadline = time.time() + 1800
    while time.time() < deadline:
        time.sleep(15)
        s = requests.get(f"{api}/generate/check/{job}", headers=headers, timeout=30).json()
        if s.get("faulted") or s.get("is_possible") is False:
            raise requests.RequestException("AI Horde job faulted")
        if s.get("done"):
            gens = requests.get(f"{api}/generate/status/{job}", headers=headers, timeout=60).json()["generations"]
            if not gens or gens[0].get("censored"):
                raise requests.RequestException("AI Horde returned no image")
            return requests.get(gens[0]["img"], timeout=120).content
    raise requests.RequestException("AI Horde timed out")


PLATE_SIZE = (768, 1344)  # master plates are painted larger, so reframed shots stay sharp


def fetch_plate(name: str, plates: dict, style: str, cache: Path) -> Path | None:
    """Paint (or reuse) the master plate `name`. A plate is a prompt, or a dict with `prompt`
    and optionally `from: <plate>` + `strength` to repaint another plate with a change."""
    spec = plates[name] if isinstance(plates[name], dict) else {"prompt": plates[name]}
    seed = int(spec.get("seed", sum(map(ord, name)) * 7))
    full = f"{spec['prompt']}. {style}"
    parent = None
    if spec.get("from"):
        parent = fetch_plate(spec["from"], plates, style, cache)
        if parent is None:
            return None
    strength = float(spec.get("strength", 0.55))
    key = f"{full}|{seed}|{parent.name if parent else ''}|{strength if parent else ''}"
    dest = cache / f"plate_{name}_{hashlib.sha1(key.encode()).hexdigest()[:12]}.jpg"
    if dest.exists():
        return dest
    print(f"  painting plate {name}" + (f" (from {spec['from']})" if parent else ""))
    for attempt in range(3):
        try:
            data = _aihorde(full, seed + attempt, PLATE_SIZE, parent, strength)
        except requests.RequestException as e:
            print(f"  ! plate {name} attempt {attempt + 1} failed: {e}")
            continue
        if data and _valid_image(data):
            Image.open(io.BytesIO(data)).convert("RGB").save(dest, quality=95)
            return dest
    return None


_unreachable: set = set()
PLACEHOLDER = "placeholder"  # the generated fog scene: not a story shot


MIN_WARMTH = 0.04  # mean red minus blue; the channel's lamp-lit frames sit around 0.05-0.2, grey ones near 0


def _warmth(img: Image.Image) -> float:
    r, _, b = np.asarray(img.resize((64, 114)), float).reshape(-1, 3).mean(0) / 255
    return float(r - b)


def fetch_ai_image(prompt: str, style: str, seed: int, cache: Path) -> Path | None:
    full = f"{prompt}. {style}"
    dest = cache / f"ai_{hashlib.sha1(f'{full}|{seed}'.encode()).hexdigest()[:16]}.jpg"
    if dest.exists():
        return dest
    # FLUX sometimes paints these prompts in plain greys. Re-roll those up to twice, nudged
    # towards colour, and keep the warmest, so every shot matches the channel's amber look.
    best, ask, try_seed = None, full, seed
    for tries_left in (2, 1, 0):
        img = _generate(ask, try_seed)
        if img is None:
            break
        if best is None or _warmth(img) > _warmth(best):
            best = img
        if _warmth(best) >= MIN_WARMTH or not tries_left:
            break
        print(f"  ! shot came out grey (warmth {_warmth(img):.2f}), repainting it")
        ask, try_seed = f"{full}, rich warm colour", try_seed + 1000
    if best is None:
        return None
    best.save(dest, quality=95)
    return dest


def _generate(full: str, seed: int) -> Image.Image | None:
    for source in (_huggingface, _pollinations, _aihorde):
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
                return Image.open(io.BytesIO(data)).convert("RGB")
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
    """Build a shot prompt the way the production bible does: camera, subject, action, evidence,
    then continuity anchors.

    The framing and subject come first because image models weight the start of a prompt most.
    A named anchor (narrator, grandmother...) is added only to shots that mention it, so the
    model draws who the shot is about and nobody else; the `world` anchor goes into every shot.
    """
    scene = line.get("scene", "")
    if not scene:
        return ""
    parts = [f"{line['camera']} shot: {scene}" if line.get("camera") else scene]
    if line.get("action"):
        parts.append(line["action"])
    if line.get("evidence"):
        parts.append(f"clearly showing {line['evidence']}")
    text = ", ".join(parts)
    if isinstance(anchors, str):
        return f"{text}. {anchors}" if anchors else text
    cast = [f"the {name}: {desc}" for name, desc in anchors.items()
            if name != "world" and name.lower() in text.lower()]
    if cast:
        text += ". " + "; ".join(cast)
    if anchors.get("world"):
        text += f". Setting: {anchors['world']}"
    return text


def resolve(line: dict, style: str, seed: int, cache: Path, used: set[int], anchors: dict | str = "",
            plates: dict | None = None) -> tuple[Path, str]:
    """Return (path, source label) for one line's visual."""
    spec, scene = line.get("visual", ""), shot_prompt(line, anchors)
    if spec and (local := find_local(spec)):
        return local, "local"
    if line.get("plate"):
        if not plates or line["plate"] not in plates:
            raise SystemExit(f"Line uses plate {line['plate']!r}, which isn't defined under plates:")
        if still := fetch_plate(line["plate"], plates, style, cache):
            return still, "plate"
    if scene and (still := fetch_ai_image(scene, style, seed, cache)):
        return still, "ai"
    if spec and (clip := fetch_pexels(spec, cache, used)):
        return clip, "pexels"
    if line.get("scene") and (clip := fetch_pexels(line["scene"], cache, used)):
        return clip, "pexels"
    # Last resort, so a render never crashes; QA fails the video if any shot ends up here.
    return generate_scene(seed, cache / f"scene_{seed}.jpg"), PLACEHOLDER


EXPOSURE = 0.17  # mean luminance a still is lifted to before the grade; the channel's frames sit at ~0.1-0.25


def _expose(img: Image.Image) -> Image.Image:
    """Lift a too-dark still with a gamma curve so it reads on a phone after the low-key grade.
    Shadows stay deep and colours keep their balance; bright stills are left alone."""
    lum = lambda im: float((np.asarray(im.resize((54, 96)), float) / 255 @ [0.299, 0.587, 0.114]).mean())
    g = 1.0
    for _ in range(3):
        mean = lum(img.point([round(255 * (i / 255) ** g) for i in range(256)] * 3)) if g < 1 else lum(img)
        if mean >= EXPOSURE - 0.01 or g <= 0.45:
            break
        g = max(0.45, g * np.log(EXPOSURE) / np.log(max(mean, 1e-3)))
    return img if g >= 1 else img.point([round(255 * (i / 255) ** g) for i in range(256)] * 3)


def _reframe(img: Image.Image, frame) -> Image.Image:
    """Cut a 9:16 shot out of a plate: frame = [centre x, centre y, zoom], x/y as 0-1 of the plate."""
    cx, cy, zoom = (list(frame) + [1.0])[:3]
    cw = min(img.width, img.height * W / H) / max(float(zoom), 1.0)
    ch = cw * H / W
    x = min(max(cx * img.width - cw / 2, 0), img.width - cw)
    y = min(max(cy * img.height - ch / 2, 0), img.height - ch)
    shot = img.crop((round(x), round(y), round(x + cw), round(y + ch)))
    if W / shot.width > 1.8:  # a tight reframe is upscaled a lot: restore some edge detail
        shot = shot.resize((W, H), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
    return shot


def _still_frames(src: Path, duration: float, move: str, shake: bool, seed: int, frame=None):
    """Yield raw RGB frames of a slow camera move over a still image."""
    frames = max(1, round(duration * FPS))
    img = Image.open(src).convert("RGB")
    if frame:
        img = _reframe(img, frame)
    img = _expose(img)
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
        # Handheld drift: two slow sines per axis, a few pixels; a little unsteadiness on impacts.
        t = f / FPS
        amp = 3.0 + (4.0 * np.exp(-t * 2) if shake else 0.0)
        hz = 1.0
        cx += amp * (np.sin(0.7 * hz * t + phase[0]) + 0.5 * np.sin(1.9 * hz * t + phase[1]))
        cy += amp * (np.sin(0.6 * hz * t + phase[2]) + 0.5 * np.sin(1.7 * hz * t + phase[3]))
        cx = min(max(cx, cw / 2), iw - cw / 2)
        cy = min(max(cy, ch / 2), ih - ch / 2)
        box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
        yield img.transform((W, H), Image.EXTENT, box, Image.BICUBIC).tobytes()


def render_segment(src: Path, duration: float, dest: Path, grade: str = "channel", move: str = "push_in",
                   impact: bool = False, seed: int = 0, frame=None):
    """Render one line's background as a 1080x1920 clip."""
    look = f"{GRADES.get(grade, GRADES['channel'])},{FINISH}"
    if impact:  # the light falters for a moment, like a lamp about to go out
        look += (",eq=brightness='if(lt(t,0.7),-0.16*(gt(sin(47*t),0.2)+gt(sin(83*t+1),0.5))*(1-t/0.7),0)'"
                 ":eval=frame")
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
    for raw in _still_frames(src, duration, move, impact, seed, frame):
        proc.stdin.write(raw)
    proc.stdin.close()
    if proc.wait():
        raise subprocess.CalledProcessError(proc.returncode, cmd)
