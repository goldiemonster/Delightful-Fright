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


def run(video: Path, lines: list[str], coverages: list[float | None], timeline, stems: dict, sr: int,
        sources: list[str] = ()) -> bool:
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

    black = _black_frames(video)
    check("No black frames", not black, ", ".join(f"{a:.1f}-{b:.1f}s" for a, b in black) or "none")

    duration = timeline[-1][2]
    check("Length 60-95 s", 60 <= duration <= 95, f"{duration:.1f} s")

    width = max(len(n) for _, n, _ in checks)
    body = "\n".join(f"{v:10s} {n:{width}s}  {d}" for v, n, d in checks)
    note = ("\n\nThese checks measure; they don't listen. Play the video once at 1.00x (and the stems in "
            "stems/ if something sounds off) before publishing.\n")
    (video.parent / "qa.txt").write_text(body + note, encoding="utf-8")
    print("  QA:\n    " + body.replace("\n", "\n    "))
    return all(v != "FAIL" for v, _, _ in checks)
