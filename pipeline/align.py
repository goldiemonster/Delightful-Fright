"""Word-level timing for captions.

The script already tells us *what* is said; we only need *when*. faster-whisper
(tiny English model, ~75 MB, CPU) listens to each narrated line and gives word
timestamps, which we match back onto the script's own words so the captions
keep your spelling and *emphasis* marks. Without it, words are spread across
the line by length, which is close but drifts on long lines.
"""
import difflib
import re

import numpy as np

_model = None
_unavailable = False


def _whisper():
    global _model, _unavailable
    if _model is None and not _unavailable:
        try:
            from faster_whisper import WhisperModel

            _model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        except Exception as e:  # not installed, or the model can't be downloaded
            print(f"  ! word timing falls back to estimates ({type(e).__name__})")
            _unavailable = True
    return _model


def _norm(word: str) -> str:
    return re.sub(r"[^a-z0-9']", "", word.lower())


def estimate(words: list[str], start: float, end: float) -> list[tuple[float, float]]:
    """Spread words over [start, end] by length (longer words take longer to say)."""
    weights = np.array([len(_norm(w)) + 2 for w in words], dtype=float)
    edges = start + (end - start) * np.concatenate([[0], np.cumsum(weights) / weights.sum()])
    return list(zip(edges[:-1], edges[1:]))


def word_times(wav: np.ndarray, sr: int, words: list[str], offset: float) -> list[tuple[float, float]]:
    """(start, end) in seconds for each script word, shifted by `offset`."""
    duration = wav.size / sr
    model = _whisper()
    if model is None or not words:
        return estimate(words, offset, offset + duration)

    audio = wav if sr == 16000 else np.interp(
        np.arange(0, wav.size, sr / 16000), np.arange(wav.size), wav
    ).astype(np.float32)
    segments, _ = model.transcribe(audio, language="en", word_timestamps=True, beam_size=1,
                                   initial_prompt=" ".join(words))
    heard = [w for seg in segments for w in (seg.words or [])]
    if not heard:
        return estimate(words, offset, offset + duration)

    times: list[tuple[float, float] | None] = [None] * len(words)
    matcher = difflib.SequenceMatcher(a=[_norm(w) for w in words], b=[_norm(h.word) for h in heard], autojunk=False)
    for a, b, n in matcher.get_matching_blocks():
        for k in range(n):
            times[a + k] = (heard[b + k].start, heard[b + k].end)

    # Fill words whisper missed or misheard by spreading them across the gap.
    i = 0
    while i < len(words):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(words) and times[j] is None:
            j += 1
        gap_start = times[i - 1][1] if i else 0.0
        gap_end = times[j][0] if j < len(words) else duration
        if gap_end <= gap_start:
            gap_end = gap_start + 0.08 * (j - i)
        times[i:j] = estimate(words[i:j], gap_start, gap_end)
        i = j

    # Keep words in order and on screen until the next one starts.
    out = []
    for k, (s, e) in enumerate(times):
        nxt = times[k + 1][0] if k + 1 < len(times) else max(e, duration)
        out.append((offset + s, offset + max(e, nxt)))
    return out
