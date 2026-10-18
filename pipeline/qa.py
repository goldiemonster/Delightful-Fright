"""Automatic checks on a finished Short, written to qa.txt next to the video.

These are measurements, not listening. They catch the defects a machine can
prove (a missing or garbled line, clipping, wrong loudness, music drowning the
voice, a silent ending, black frames), so a human listening pass can focus on
whether it actually sounds good. Each check reports PASS, FAIL or UNVERIFIED.
"""
import re
import subprocess
from pathlib import Path

import numpy as np

from . import hands

SYNC_TOLERANCE = 0.25  # seconds a caption may lead or trail the voice it shows
LINE_MIN_COVERAGE = 0.85  # share of a line's words the recogniser must hear
VOICE_OVER_BED_DB = 8.0  # voice must sit this far above music + effects while speaking


def _db(x: float) -> float:
    return 20 * np.log10(max(x, 1e-9))


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x**2))) if x.size else 0.0


def _loudness(video: Path) -> tuple[float, float]:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    summary = err[err.rindex("Summary:"):]
    return (float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary).group(1)),
            float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary).group(1)))


def _black_frames(video: Path) -> list[tuple[float, float]]:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", "blackdetect=d=0.4:pix_th=0.06",
                          "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]


def _voice_onsets(voice: np.ndarray, sr: int, timeline) -> list[float | None]:
    """When each line's voice actually starts in the mix, from the voice stem's energy."""
    hop = int(0.01 * sr)
    onsets = []
    for start, end, _ in timeline:
        # Look from just before the line: any earlier and the last line's reverb tail reads as an onset.
        a, b = max(0, int((start - 0.1) * sr)), int(min(end, start + 1.5) * sr)
        seg = voice[a:b]
        if seg.size < hop * 3:
            onsets.append(None)
            continue
        env = np.sqrt(np.convolve(seg**2, np.ones(hop * 2) / (hop * 2), mode="same"))[::hop]
        above = np.nonzero(env > 0.15 * env.max())[0]
        onsets.append(a / sr + above[0] * hop / sr if above.size else None)
    return onsets


def contact_sheet(video: Path, timeline, dest: Path, cols: int = 5):
    """One frame from the middle of every shot, tiled, to review continuity at a glance."""
    from PIL import Image, ImageDraw
    w, h = 216, 384
    rows = -(-len(timeline) // cols)
    sheet = Image.new("RGB", (w * cols, h * rows))
    draw = ImageDraw.Draw(sheet)
    for i, (start, _, end) in enumerate(timeline):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{(start + end) / 2:.2f}", "-i", str(video),
                              "-frames:v", "1", "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) == w * h * 3:
            sheet.paste(Image.frombytes("RGB", (w, h), raw), ((i % cols) * w, (i // cols) * h))
        draw.text(((i % cols) * w + 6, (i // cols) * h + 6), str(i + 1), fill=(255, 220, 0))
    sheet.save(dest, quality=85)


def run(video: Path, lines: list[str], coverages: list[float | None], timeline, stems: dict, sr: int,
        sources: list[str] = (), word_times=None) -> bool:
    """Write qa.txt beside the video; return True when nothing FAILED."""
    checks = []

    def check(name, ok, detail):
        checks.append(("UNVERIFIED" if ok is None else "PASS" if ok else "FAIL", name, detail))

    # Narration: every line spoken completely and in order.
    if all(c is None for c in coverages):
        check("Narration complete", None, "no speech recogniser available, so no line was checked")
    else:
        weak = [(i + 1, c) for i, c in enumerate(coverages) if c is not None and c < LINE_MIN_COVERAGE]
        detail = ", ".join(f"line {i} heard {c:.0%}" for i, c in weak) or \
            f"all {len(lines)} lines heard (lowest {min(c for c in coverages if c is not None):.0%})"
        check("Narration complete", not weak, detail)

    # Loudness and peaks of the actual export.
    lufs, peak = _loudness(video)
    check("Loudness", -15.0 <= lufs <= -13.0, f"{lufs:.1f} LUFS (target -14)")
    check("True peak", peak <= -1.0, f"{peak:.1f} dBTP (limit -1.0)")

    voice = stems["voice"]
    bed = stems["music"] + stems["effects"]
    mix = voice + bed

    # Voice clearly above the bed while the narrator is speaking.
    speaking = np.zeros(voice.size, dtype=bool)
    for start, end, _ in timeline:
        speaking[int(start * sr): int(end * sr)] = True
    ratio = _db(_rms(voice[speaking])) - _db(_rms(bed[speaking]))
    check("Voice above music and effects", ratio >= VOICE_OVER_BED_DB, f"{ratio:.1f} dB (need {VOICE_OVER_BED_DB:.0f})")

    # Captions in sync: each line's first caption word appears when its voice starts.
    if word_times:
        offsets = [(i + 1, words[0][0] - onset) for i, (words, onset)
                   in enumerate(zip(word_times, _voice_onsets(voice, sr, timeline))) if words and onset is not None]
        late = [(i, d) for i, d in offsets if abs(d) > SYNC_TOLERANCE]
        worst = max((abs(d) for _, d in offsets), default=0.0)
        check("Captions in sync", not late,
              ", ".join(f"line {i} {d:+.2f}s" for i, d in late) or f"every line within {worst:.2f}s of its voice")

    # The ending: last line fully heard, and the last 10 seconds aren't dead air.
    tail = mix[-10 * sr:]
    tail_db = _db(_rms(tail))
    last = coverages[-1]
    check("Ending audible", (tail_db > -40) and (last is None or last >= LINE_MIN_COVERAGE),
          f"last 10 s at {tail_db:.0f} dBFS RMS" + ("" if last is None else f", final line heard {last:.0%}"))

    # Every shot must be a story shot, never the generic fog placeholder.
    if sources:
        missing = [i + 1 for i, s in enumerate(sources) if s == "placeholder"]
        check("Story shots", not missing,
              f"lines {', '.join(map(str, missing))} fell back to a placeholder (no image source reachable)"
              if missing else f"all {len(sources)} shots from the shot list")

    # Hands: every painting was shown to a vision model that counts fingers (see hands.py).
    if hands.REPORT:
        bad = [f"{n}: {v.get('problem')}" for n, v in hands.REPORT.items() if v.get("ok") is False]
        unchecked = [n for n, v in hands.REPORT.items() if v.get("ok") is None]
        check("Hands anatomically correct", False if bad else None if unchecked else True,
              "; ".join(bad) or (f"{len(unchecked)} of {len(hands.REPORT)} paintings not checked "
                                 "(needs ANTHROPIC_API_KEY): look at the hands yourself" if unchecked else
                                 f"all {len(hands.REPORT)} paintings checked"))

    black = _black_frames(video)
    check("No black frames", not black, ", ".join(f"{a:.1f}-{b:.1f}s" for a, b in black) or "none")

    duration = timeline[-1][2]
    check("Length 60-95 s", 60 <= duration <= 95, f"{duration:.1f} s")

    width = max(len(n) for _, n, _ in checks)
    body = "\n".join(f"{v:10s} {n:{width}s}  {d}" for v, n, d in checks)
    note = ("\n\nThese checks measure; they don't listen or look. Check contact_sheet.jpg for the same faces, "
            "rooms and props in every shot, then play the video once at 1.00x (and the stems in stems/ if "
            "something sounds off) before publishing.\n")
    (video.parent / "qa.txt").write_text(body + note, encoding="utf-8")
    contact_sheet(video, timeline, video.parent / "contact_sheet.jpg")
    print("  QA:\n    " + body.replace("\n", "\n    "))
    return all(v != "FAIL" for v, _, _ in checks)
