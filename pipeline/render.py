"""Turn a story YAML into a finished, vertical YouTube Short.

    python -m pipeline.render stories/never-answer-the-third-knock.yaml
"""
import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from . import align, audio, captions, qa, tts, visuals

ROOT = Path(__file__).resolve().parent.parent
PAUSE_AFTER_HOOK = 0.7
PAUSE = 0.45
END_HOLD = 1.6
LONG_WARNING = 95.0
LOUDNESS = "loudnorm=I=-14:TP=-1.5:LRA=11"  # YouTube's playback loudness


def loudness_filter(wav: Path) -> str:
    """Two-pass loudnorm: measure first, so the final pass lands exactly on target."""
    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(wav), "-af", LOUDNESS + ":print_format=json", "-f", "null", "-"],
        check=True, capture_output=True, text=True,
    ).stderr
    m = json.loads(probe[probe.rindex("{"): probe.rindex("}") + 1])
    return (
        f"{LOUDNESS}:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
        f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}"
    )


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
    seed_base = sum(map(ord, slug))
    print(f"Rendering “{story['title']}” ({len(lines)} lines)")

    # 1. Narration, one line at a time so we know exactly when each line starts.
    narrator = tts.get_tts(story.get("voice", "bm_george"), float(story.get("speed", 0.92)), engine,
                           story.get("cartesia_voice"), story.get("cartesia_model", "sonic-3"))
    print(f"  narrator: {narrator.name}")
    clips, timeline, word_times, coverages, t, sr = [], [], [], [], 0.0, None
    for i, line in enumerate(lines):
        wav, sr = narrator.synth(captions.strip_markup(line["text"]))
        wav = tts.trim_silence(wav, sr)
        speak = wav.size / sr
        gap = PAUSE_AFTER_HOOK if i == 0 else PAUSE
        gap = float(line.get("pause", gap)) + (END_HOLD if i == len(lines) - 1 else 0)
        timeline.append((t, t + speak, t + speak + gap))
        script_words = [w for w, _ in captions.words(line["text"])]
        times, heard = align.word_times(wav, sr, script_words, t)
        word_times.append(times)
        coverages.append(align.coverage(script_words, heard))
        clips.append(np.concatenate([wav, np.zeros(int(gap * sr), dtype=np.float32)]))
        t += speak + gap
    narration = np.concatenate(clips)
    total = narration.size / sr
    print(f"  length: {total:.1f}s" + (f"  ! over {LONG_WARNING:.0f}s: consider trimming" if total > LONG_WARNING else ""))

    # 2. Sound: processed voice, an eerie score (or your track), a low swell under impacts, story effects.
    impacts = [timeline[i][0] for i, line in enumerate(lines) if i == 0 or line.get("impact")]
    cuts = [start for start, _, _ in timeline[1:]]
    sfx = []
    for line, (start, _, _) in zip(lines, timeline):
        names = line.get("sfx") or []
        for name in [names] if isinstance(names, str) else names:
            if name not in audio.SFX:
                raise SystemExit(f"Unknown sfx {name!r}. Choose from: {', '.join(audio.SFX)}")
            sfx.append((start, name))
    music = story.get("music")
    music_path = ROOT / music if music and music not in ("auto", "none") else None
    mixed, stems = audio.mix(narration, sr, work, impacts, cuts, sfx, music_path,
                             music_level=0.0 if music == "none" else float(story.get("music_level", 0.14)),
                             room=story.get("ambience", "room"), seed=seed_base)
    sf.write(work / "audio.wav", mixed, sr)
    (out_dir / "stems").mkdir(exist_ok=True)
    for name, stem in stems.items():
        sf.write(out_dir / "stems" / f"{name}.wav", stem, sr)

    # 3. Visuals: one shot per line.
    style = story.get("style", visuals.DEFAULT_STYLE)
    grade = story.get("grade", "channel")
    anchors = story.get("anchors") or ""
    used: set[int] = set()
    sources = []
    concat = []
    for i, (line, (start, _, end)) in enumerate(zip(lines, timeline)):
        src, label = visuals.resolve(line, style, seed_base + i, cache, used, anchors, story.get("plates"))
        sources.append(label)
        seg = work / f"seg_{i:02d}.mp4"
        impact = i == 0 or bool(line.get("impact"))
        move = line.get("move", visuals.MOVES[i % len(visuals.MOVES)])
        visuals.render_segment(src, end - start, seg, grade, move, impact and i > 0, seed_base + i, line.get("frame"))
        concat.append(f"file '{seg.name}'")
        what = f"{line['plate']} {line.get('frame', '')}" if label == "plate" else line.get("scene") or line.get("visual", "")
        print(f"  [{i + 1}/{len(lines)}] {label:9s} {what}"[:110])
    (work / "segments.txt").write_text("\n".join(concat) + "\n")

    # 4. Captions, with the title card over the hook.
    captions.build_ass(
        [(line["text"], times) for line, times in zip(lines, word_times)],
        work / "captions.ass",
        title=story.get("title") if story.get("title_card", True) else None,
        title_end=timeline[0][2],
    )

    # 5. Final mix: video + captions + loudness-normalised audio.
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
            "-vf", ass, "-af", loudness_filter(work / "audio.wav"), "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-r", str(visuals.FPS),
            "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
            "-shortest", "-movflags", "+faststart", str(final.resolve()),
        ],
        check=True,
        cwd=work,
    )
    # A cover frame from the hook, for the Shorts thumbnail picker.
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{min(1.2, total / 2):.2f}", "-i", str(final),
                    "-frames:v", "1", "-q:v", "2", str(out_dir / "cover.jpg")], check=True)

    # 6. Upload copy: title, description, tags, ready to paste.
    yt = story.get("youtube", {})
    meta = [
        f"TITLE:\n{yt.get('title', story['title'] + ' | Delightful Fright')}\n",
        f"DESCRIPTION:\n{yt.get('description', '').strip()}\n",
        f"TAGS:\n{', '.join(yt.get('tags', []))}\n",
        "REMINDER: the visuals and voice are AI-made, so tick “Altered or synthetic content” in YouTube Studio.\n",
    ]
    (out_dir / "upload.txt").write_text("\n".join(meta), encoding="utf-8")

    passed = qa.run(final, [line["text"] for line in lines], coverages, timeline, stems, sr, sources, word_times)
    if not passed:
        print("  ! QA found problems: see qa.txt before publishing")

    if not keep_work:
        shutil.rmtree(work)
    print(f"Done → {final}")
    return final


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stories", nargs="+", type=Path, help="story YAML file(s)")
    ap.add_argument("--out", type=Path, default=ROOT / "out")
    ap.add_argument("--engine", choices=["auto", "kokoro", "cartesia", "espeak"], default="auto")
    ap.add_argument("--keep-work", action="store_true", help="keep intermediate files for debugging")
    args = ap.parse_args()
    for story in args.stories:
        render(story, args.out, args.engine, args.keep_work)


if __name__ == "__main__":
    main()
