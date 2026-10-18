"""Turn a story YAML into a finished, vertical YouTube Short.

    python -m pipeline.render stories/never-answer-the-third-knock.yaml
"""
import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from . import audio, captions, tts, visuals

ROOT = Path(__file__).resolve().parent.parent
PAUSE_AFTER_HOOK = 0.55
PAUSE = 0.32
END_HOLD = 1.2
SHORTS_TARGET = 60.0


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def render(story_path: Path, out_root: Path, engine: str, keep_work: bool) -> Path:
    story = yaml.safe_load(story_path.read_text(encoding="utf-8"))
    slug = story.get("slug") or slugify(story["title"])
    out_dir = out_root / slug
    work = out_dir / "work"
    cache = ROOT / "cache"
    for d in (work, cache):
        d.mkdir(parents=True, exist_ok=True)

    lines = story["lines"]
    print(f"Rendering “{story['title']}” ({len(lines)} lines)")

    # 1. Narration, one line at a time so we know exactly when each line starts.
    narrator = tts.get_tts(story.get("voice", "bm_george"), float(story.get("speed", 0.92)), engine)
    print(f"  narrator: {narrator.name}")
    clips, timeline, t, sr = [], [], 0.0, None
    for i, line in enumerate(lines):
        wav, sr = narrator.synth(captions.strip_markup(line["text"]))
        wav = tts.trim_silence(wav, sr)
        speak = wav.size / sr
        gap = PAUSE_AFTER_HOOK if i == 0 else PAUSE
        gap = float(line.get("pause", gap)) + (END_HOLD if i == len(lines) - 1 else 0)
        timeline.append((t, t + speak, t + speak + gap))
        clips.append(np.concatenate([wav, np.zeros(int(gap * sr), dtype=np.float32)]))
        t += speak + gap
    narration = np.concatenate(clips)
    total = narration.size / sr
    print(f"  length: {total:.1f}s" + ("  ! over 60s: consider trimming for Shorts" if total > SHORTS_TARGET else ""))

    # 2. Sound design: echo on the voice, a drone, and booms on the hook and any `impact: true` lines.
    impacts = [timeline[i][0] for i, line in enumerate(lines) if i == 0 or line.get("impact")]
    sf.write(work / "audio.wav", audio.mix(narration, sr, impacts), sr)

    # 3. Visuals: one background per line.
    used: set[int] = set()
    seed_base = sum(map(ord, slug))
    concat = []
    for i, (line, (start, _, end)) in enumerate(zip(lines, timeline)):
        src, label = visuals.resolve(line.get("visual", ""), seed_base + i, cache, used)
        seg = work / f"seg_{i:02d}.mp4"
        visuals.render_segment(src, end - start, seg, zoom_in=i % 2 == 0)
        concat.append(f"file '{seg.name}'")
        print(f"  [{i + 1}/{len(lines)}] {label:9s} {line.get('visual', '')}")
    (work / "segments.txt").write_text("\n".join(concat) + "\n")

    # 4. Captions.
    captions.build_ass([(s, e, line["text"]) for line, (s, e, _) in zip(lines, timeline)], work / "captions.ass")

    # 5. Final mix: video + captions + audio.
    final = out_dir / f"{slug}.mp4"
    ass = "ass=captions.ass"
    fonts = ROOT / "assets" / "fonts"
    if any(fonts.glob("*.[ot]tf")):
        ass += f":fontsdir={os.path.relpath(fonts, work)}"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", "segments.txt",
            "-i", "audio.wav",
            "-vf", ass, "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-shortest", "-movflags", "+faststart", str(final.resolve()),
        ],
        check=True,
        cwd=work,
    )

    # 6. Upload copy: title, description, tags, ready to paste.
    yt = story.get("youtube", {})
    meta = [
        f"TITLE:\n{yt.get('title', story['title'])}\n",
        f"DESCRIPTION:\n{yt.get('description', '').strip()}\n",
        f"TAGS:\n{', '.join(yt.get('tags', []))}\n",
        "REMINDER: if any visuals or voices look/sound realistic and are AI-made, tick "
        "“Altered or synthetic content” in YouTube Studio.\n",
    ]
    (out_dir / "upload.txt").write_text("\n".join(meta), encoding="utf-8")

    if not keep_work:
        shutil.rmtree(work)
    print(f"Done → {final}")
    return final


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stories", nargs="+", type=Path, help="story YAML file(s)")
    ap.add_argument("--out", type=Path, default=ROOT / "out")
    ap.add_argument("--engine", choices=["auto", "kokoro", "espeak"], default="auto")
    ap.add_argument("--keep-work", action="store_true", help="keep intermediate files for debugging")
    args = ap.parse_args()
    for story in args.stories:
        render(story, args.out, args.engine, args.keep_work)


if __name__ == "__main__":
    main()
