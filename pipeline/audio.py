"""Sound: narrator processing, a generated horror score, and sound effects.

Everything here is synthesised in code, so there is no music licensing to worry
about. Drop your own royalty-free track in assets/music/ and set `music:` in the
story to use it instead of the generated score.
"""
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal

# ---------------------------------------------------------------- helpers


def _t(seconds: float, sr: int) -> np.ndarray:
    return np.arange(int(seconds * sr)) / sr


def _lowpass(x: np.ndarray, sr: int, hz: float, order: int = 2) -> np.ndarray:
    sos = signal.butter(order, min(hz, sr * 0.45), "low", fs=sr, output="sos")
    return signal.sosfilt(sos, x)


def _highpass(x: np.ndarray, sr: int, hz: float, order: int = 2) -> np.ndarray:
    sos = signal.butter(order, hz, "high", fs=sr, output="sos")
    return signal.sosfilt(sos, x)


def _bandpass(x: np.ndarray, sr: int, lo: float, hi: float) -> np.ndarray:
    sos = signal.butter(2, [lo, min(hi, sr * 0.45)], "band", fs=sr, output="sos")
    return signal.sosfilt(sos, x)


def _impulse_response(sr: int, seconds: float, damp_hz: float, seed: int) -> np.ndarray:
    """A synthetic room/hall: decaying noise that loses its highs as it fades."""
    rng = np.random.default_rng(seed)
    t = _t(seconds, sr)
    ir = rng.standard_normal(t.size) * np.exp(-t * 6.9 / seconds)  # -60 dB at `seconds`
    ir = _lowpass(ir, sr, damp_hz)
    ir[: int(0.012 * sr)] = 0  # pre-delay
    return ir / np.sqrt(np.sum(ir**2))


def reverb(x: np.ndarray, sr: int, seconds: float = 1.6, wet: float = 0.25, damp_hz: float = 5000, seed: int = 7):
    wet_sig = signal.fftconvolve(x, _impulse_response(sr, seconds, damp_hz, seed))[: x.size]
    return (1 - wet) * x + wet * wet_sig


def _place(out: np.ndarray, clip: np.ndarray, at: float, sr: int, gain: float = 1.0):
    i = max(0, int(at * sr))
    j = min(out.size, i + clip.size)
    if j > i:
        out[i:j] += gain * clip[: j - i]


def _fade(x: np.ndarray, sr: int, fade_in: float, fade_out: float) -> np.ndarray:
    env = np.ones(x.size)
    a, b = int(fade_in * sr), int(fade_out * sr)
    if a:
        env[:a] = np.linspace(0, 1, a)
    if b:
        env[-b:] = np.minimum(env[-b:], np.linspace(1, 0, b))
    return x * env


# ---------------------------------------------------------------- narrator


def process_voice(voice: np.ndarray, sr: int, work: Path) -> np.ndarray:
    """Broadcast-style voice chain: clean lows, warmth, presence, compression, small room."""
    raw, done = work / "voice_raw.wav", work / "voice_eq.wav"
    sf.write(raw, voice, sr)
    chain = (
        "highpass=f=75,"
        "equalizer=f=160:t=q:w=1.0:g=2.5,"  # chest
        "equalizer=f=450:t=q:w=1.2:g=-2,"  # less boxy
        "equalizer=f=3200:t=q:w=1.4:g=3,"  # presence, cuts through music on phone speakers
        "equalizer=f=7500:t=q:w=2:g=-2,"  # tame Kokoro's hiss
        "acompressor=threshold=-22dB:ratio=3.5:attack=4:release=140:makeup=5dB,"
        "alimiter=limit=0.89"
    )
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", chain, str(done)], check=True)
    out, _ = sf.read(done, dtype="float32")
    return reverb(out, sr, seconds=0.9, wet=0.14, damp_hz=4500).astype(np.float32)


# ---------------------------------------------------------------- sound effects


def boom(sr: int, length: float = 3.0) -> np.ndarray:
    """Cinematic low impact with a sub drop and a dark tail."""
    t = _t(length, sr)
    freq = 90 * np.exp(-t * 3.0) + 32
    hit = np.sin(2 * np.pi * np.cumsum(freq) / sr) * np.exp(-t * 1.6)
    crack = _lowpass(np.random.default_rng(1).standard_normal(t.size), sr, 2500) * np.exp(-t * 14) * 0.6
    return reverb(np.tanh(1.6 * (hit + crack)), sr, seconds=2.5, wet=0.35, damp_hz=2500).astype(np.float32)


def riser(sr: int, length: float = 1.8) -> np.ndarray:
    """Builds tension into an impact: rising filtered noise and a climbing whine."""
    t = _t(length, sr)
    rng = np.random.default_rng(3)
    noise = rng.standard_normal(t.size)
    # crossfade three filtered copies so the noise brightens as it rises
    bands = [_bandpass(noise, sr, lo, hi) for lo, hi in ((200, 900), (800, 3000), (2500, 9000))]
    pos = t / length
    shaped = bands[0] * (1 - pos) + bands[1] * np.sin(np.pi * pos) + bands[2] * pos
    whine = np.sin(2 * np.pi * np.cumsum(300 + 900 * pos**2) / sr) * 0.25
    out = (shaped + whine) * pos**2.2
    return (out / (np.max(np.abs(out)) + 1e-9)).astype(np.float32)


def whoosh(sr: int, length: float = 0.7) -> np.ndarray:
    t = _t(length, sr)
    noise = np.random.default_rng(5).standard_normal(t.size)
    env = np.sin(np.pi * t / length) ** 2
    out = _bandpass(noise, sr, 300, 2400) * env
    return (out / (np.max(np.abs(out)) + 1e-9)).astype(np.float32)


def knock(sr: int, count: int = 3, gap: float = 0.42) -> np.ndarray:
    """Knuckles on a heavy wooden door."""
    t = _t(0.25, sr)
    one = (np.sin(2 * np.pi * 95 * t) + 0.5 * np.sin(2 * np.pi * 210 * t)) * np.exp(-t * 38)
    one += _bandpass(np.random.default_rng(2).standard_normal(t.size), sr, 400, 2500) * np.exp(-t * 90) * 0.5
    out = np.zeros(int((gap * (count - 1) + 0.4) * sr))
    for k in range(count):
        _place(out, one, k * gap, sr)
    return reverb(out, sr, seconds=1.2, wet=0.3).astype(np.float32)


def heartbeat(sr: int, beats: int = 6, bpm: float = 72) -> np.ndarray:
    t = _t(0.18, sr)
    thump = np.sin(2 * np.pi * 48 * t) * np.exp(-t * 28)
    out = np.zeros(int((beats * 60 / bpm + 0.4) * sr))
    for k in range(beats):
        at = k * 60 / bpm
        _place(out, thump, at, sr)
        _place(out, thump * 0.6, at + 0.22, sr)
    return np.tanh(2 * out).astype(np.float32)


def bell(sr: int, length: float = 5.0) -> np.ndarray:
    """A distant, out-of-tune church bell."""
    t = _t(length, sr)
    partials = [(1.0, 1.0), (2.01, 0.6), (2.43, 0.45), (3.0, 0.3), (4.17, 0.25), (5.4, 0.15)]
    out = sum(a * np.sin(2 * np.pi * 196 * r * t) * np.exp(-t * (0.9 + r * 0.5)) for r, a in partials)
    return reverb(out / 2.5, sr, seconds=3.5, wet=0.5, damp_hz=3000).astype(np.float32)


def static(sr: int, length: float = 1.5) -> np.ndarray:
    t = _t(length, sr)
    rng = np.random.default_rng(9)
    crackle = rng.standard_normal(t.size) * (rng.random(t.size) < 0.02) * 2
    out = _bandpass(rng.standard_normal(t.size) * 0.4 + crackle, sr, 900, 6000)
    return _fade(out / (np.max(np.abs(out)) + 1e-9), sr, 0.05, 0.3).astype(np.float32)


SFX = {"boom": boom, "riser": riser, "whoosh": whoosh, "knock": knock,
       "heartbeat": heartbeat, "bell": bell, "static": static}


# ---------------------------------------------------------------- score


def _tone(freq: float, t: np.ndarray, harmonics: int = 6, detune: float = 0.0) -> np.ndarray:
    """A soft saw-like tone (fewer harmonics = darker)."""
    out = np.zeros(t.size)
    for f in (freq * (1 - detune), freq * (1 + detune)):
        for n in range(1, harmonics + 1):
            out += np.sin(2 * np.pi * f * n * t + n) / n
    return out


def score(duration: float, sr: int, seed: int, impacts: list[float]) -> np.ndarray:
    """A slow, dissonant ambient bed: drone, breathing pad, sparse piano, sub pulses."""
    rng = np.random.default_rng(seed)
    t = _t(duration, sr)
    root = float(rng.choice([43.65, 46.25, 49.0, 51.91, 55.0]))  # F1 .. A1

    drone = _tone(root, t, harmonics=4, detune=0.004) * 0.5 + _tone(root * 1.5, t, harmonics=3, detune=0.006) * 0.2
    drone = _lowpass(drone, sr, 220)

    # Pad: minor chord plus a cluster note that slowly fades in and out of tune.
    pad = sum(_tone(root * 4 * r, t, harmonics=5, detune=0.003) for r in (1.0, 1.189, 1.498))
    pad += 0.6 * _tone(root * 4 * 1.414, t, harmonics=4, detune=0.008) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.03 * t))
    breath = 0.55 + 0.45 * np.sin(2 * np.pi * (1 / 9) * t + rng.uniform(0, 6))
    pad = _lowpass(pad, sr, 900) * breath * 0.18

    # Sparse piano: a falling minor motif, one note every few seconds, drenched in reverb.
    piano = np.zeros(t.size)
    scale = [1.0, 1.189, 1.335, 1.498, 1.587, 2.0]
    at = 2.5
    note_t = _t(4.0, sr)
    while at < duration - 3:
        f = root * 8 * float(rng.choice(scale)) * float(rng.choice([1, 0.5]))
        note = sum(np.sin(2 * np.pi * f * n * note_t) * np.exp(-note_t * (1.2 + n * 0.9)) / n**1.5 for n in range(1, 6))
        _place(piano, note * np.minimum(1, note_t / 0.004), at, sr, 0.3)
        at += float(rng.uniform(3.0, 6.5))
    piano = reverb(piano, sr, seconds=4.0, wet=0.55, damp_hz=3500)

    bed = drone + pad + piano
    bed = reverb(bed, sr, seconds=3.0, wet=0.3, damp_hz=3000)

    # Pull the bed out just before each impact so the hit lands in near-silence.
    env = np.ones(t.size)
    for hit in impacts:
        a, b, c = int((hit - 1.0) * sr), int(hit * sr), int((hit + 2.5) * sr)
        if 0 < a and b < env.size:
            env[a:b] = np.minimum(env[a:b], np.linspace(1, 0.15, b - a))
            n = env[b:c].size
            env[b:c] = np.minimum(env[b:c], np.linspace(0.15, 1, c - b)[:n])
    bed *= env
    bed = _fade(bed, sr, 1.5, 2.0)
    return (bed / (np.max(np.abs(bed)) + 1e-9)).astype(np.float32)


def load_music(path: Path, duration: float, sr: int) -> np.ndarray:
    """Decode any audio file with ffmpeg, loop it to length, and fade it out."""
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
        check=True, capture_output=True,
    ).stdout
    music = np.frombuffer(raw, dtype=np.float32)
    reps = int(np.ceil(duration * sr / max(1, music.size)))
    music = np.tile(music, reps)[: int(duration * sr)]
    return _fade(music / (np.max(np.abs(music)) + 1e-9), sr, 0.5, 2.5).astype(np.float32)


# ---------------------------------------------------------------- mix


def _duck(narration: np.ndarray, sr: int, depth: float) -> np.ndarray:
    """Gain curve that dips the music while the narrator speaks."""
    win = int(0.05 * sr)
    level = np.sqrt(np.convolve(narration**2, np.ones(win) / win, mode="same"))
    speaking = (level > 0.02).astype(float)
    smooth = np.convolve(speaking, np.hanning(int(0.4 * sr)) / (0.2 * sr), mode="same")
    return 1 - depth * np.clip(smooth, 0, 1)


def mix(narration: np.ndarray, sr: int, work: Path, impacts: list[float], cuts: list[float],
        sfx: list[tuple[float, str]], music: Path | None = None, music_level: float = 0.32,
        seed: int = 0) -> np.ndarray:
    total = narration.size
    voice = process_voice(narration, sr, work)
    voice = np.pad(voice, (0, max(0, total - voice.size)))[:total]

    bed = load_music(music, total / sr, sr) if music else score(total / sr, sr, seed, impacts)
    bed = bed * _duck(narration, sr, depth=0.45) * music_level

    fx = np.zeros(total, dtype=np.float32)
    hit, rise, swish = boom(sr), riser(sr), whoosh(sr)
    for at in impacts:
        _place(fx, rise, at - rise.size / sr, sr, 0.22)
        _place(fx, hit, at, sr, 0.75)
    for at in cuts:
        _place(fx, swish, at - 0.35, sr, 0.06)
    for at, name in sfx:
        _place(fx, SFX[name](sr), at, sr, 0.5)

    out = voice + bed + fx
    return (out / (np.max(np.abs(out)) + 1e-9) * 0.89).astype(np.float32)
