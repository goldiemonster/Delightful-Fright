"""Sound design generated from scratch: no music licensing to worry about."""
import numpy as np


def _delay(x: np.ndarray, sr: int, seconds: float) -> np.ndarray:
    n = int(seconds * sr)
    return np.concatenate([np.zeros(n, dtype=x.dtype), x[:-n]]) if n else x


def eerie_voice(voice: np.ndarray, sr: int) -> np.ndarray:
    """A short, roomy echo so the narrator sounds like they're in an empty house."""
    wet = 0.22 * _delay(voice, sr, 0.045) + 0.14 * _delay(voice, sr, 0.083) + 0.08 * _delay(voice, sr, 0.17)
    return voice + wet


def drone(duration: float, sr: int, seed: int = 0) -> np.ndarray:
    """A slow-beating low drone with dark rumbling noise underneath."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(duration * sr)) / sr
    lfo = 0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t + rng.uniform(0, 6))
    tone = (
        np.sin(2 * np.pi * 55.0 * t)
        + 0.8 * np.sin(2 * np.pi * 55.6 * t)  # detuned: slow, uneasy beating
        + 0.35 * np.sin(2 * np.pi * 82.4 * t)
        + 0.15 * np.sin(2 * np.pi * 116.5 * t)  # tritone above, for dread
    ) * lfo
    brown = np.cumsum(rng.standard_normal(t.size))
    brown -= np.convolve(brown, np.ones(sr) / sr, mode="same")  # remove slow drift
    brown /= np.max(np.abs(brown)) + 1e-9
    out = tone / 2.5 + 0.5 * brown
    fade = min(1.5, duration / 4)
    env = np.clip(np.minimum(t / fade, (duration - t) / fade), 0, 1)
    return (out * env).astype(np.float32)


def boom(sr: int, length: float = 2.5) -> np.ndarray:
    """A cinematic low impact for the hook and the twist."""
    t = np.arange(int(length * sr)) / sr
    freq = 70 * np.exp(-t * 1.5) + 30
    phase = 2 * np.pi * np.cumsum(freq) / sr
    hit = np.sin(phase) * np.exp(-t * 2.2)
    noise = np.random.default_rng(1).standard_normal(t.size) * np.exp(-t * 18) * 0.3
    return (hit + noise).astype(np.float32)


def mix(narration: np.ndarray, sr: int, impacts: list[float], drone_level: float = 0.09) -> np.ndarray:
    total = narration.size
    out = eerie_voice(narration, sr)
    out = out + drone_level * drone(total / sr, sr)
    hit = boom(sr) * 0.55
    for at in impacts:
        i = int(at * sr)
        j = min(total, i + hit.size)
        out[i:j] += hit[: j - i]
    peak = np.max(np.abs(out)) + 1e-9
    return (out / peak * 0.89).astype(np.float32)  # about -1 dBFS
