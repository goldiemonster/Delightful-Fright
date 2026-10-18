"""Text-to-speech engines.

Kokoro (open-source, runs locally, free) is the default narrator. Cartesia
Sonic (the voices the channel's published episodes use, e.g. Charlotte) is used
when the story sets `cartesia_voice` and CARTESIA_API_KEY is available. eSpeak
is a robotic-sounding fallback used only when the Kokoro model files are
missing, so the pipeline can still be tested end to end.

Speech is never time-stretched: what the engine says is what plays, at 1.00x.
"""
import ctypes
import os
from pathlib import Path

import numpy as np

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
KOKORO_MODEL = MODELS_DIR / "kokoro-v1.0.onnx"
KOKORO_VOICES = MODELS_DIR / "voices-v1.0.bin"


class KokoroTTS:
    name = "kokoro"

    def __init__(self, voice: str, speed: float):
        from kokoro_onnx import Kokoro

        self.engine = Kokoro(str(KOKORO_MODEL), str(KOKORO_VOICES))
        self.voice = self._blend(voice) if "," in voice or ":" in voice else voice
        self.speed = speed

    def _blend(self, spec: str):
        """'am_onyx:0.6,bm_george:0.4' mixes voices into one narrator."""
        names, weights = [], []
        for part in spec.split(","):
            name, _, weight = part.strip().partition(":")
            names.append(name)
            weights.append(float(weight or 1))
        weights = np.array(weights) / sum(weights)
        styles = [self.engine.get_voice_style(n) for n in names]
        return sum(w * s for w, s in zip(weights, styles))

    def synth(self, text: str):
        samples, sr = self.engine.create(text, voice=self.voice, speed=self.speed, lang="en-us")
        return np.asarray(samples, dtype=np.float32), sr


class CartesiaTTS:
    name = "cartesia"
    SR = 44100

    def __init__(self, voice_id: str, model: str = "sonic-3"):
        import requests

        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": os.environ["CARTESIA_API_KEY"],
            "Cartesia-Version": "2025-04-16",
        })
        self.voice_id = voice_id
        self.model = model

    def synth(self, text: str):
        r = self.session.post(
            "https://api.cartesia.ai/tts/bytes",
            json={
                "model_id": self.model,
                "transcript": text,
                "voice": {"mode": "id", "id": self.voice_id},
                "language": "en",
                "output_format": {"container": "raw", "encoding": "pcm_f32le", "sample_rate": self.SR},
            },
            timeout=120,
        )
        r.raise_for_status()
        return np.frombuffer(r.content, dtype=np.float32).copy(), self.SR


_SYNTH_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p)


class EspeakTTS:
    name = "espeak (fallback)"

    def __init__(self, voice: str, speed: float):
        import espeakng_loader

        data_path = espeakng_loader.get_data_path()
        os.environ.setdefault("ESPEAK_DATA_PATH", data_path)
        lib = ctypes.cdll.LoadLibrary(espeakng_loader.get_library_path())
        lib.espeak_Initialize.restype = ctypes.c_int
        lib.espeak_Synth.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int,
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint), ctypes.c_void_p,
        ]
        # 2 = AUDIO_OUTPUT_SYNCHRONOUS: samples are delivered to our callback.
        self.sr = lib.espeak_Initialize(2, 0, str(Path(data_path).parent).encode(), 0)
        self._chunks = []

        def on_audio(wav, n, _events):
            if wav and n > 0:
                self._chunks.append(np.ctypeslib.as_array(wav, shape=(n,)).copy())
            return 0

        self._callback = _SYNTH_CALLBACK(on_audio)  # keep a reference so it isn't GC'd
        lib.espeak_SetSynthCallback(self._callback)
        lib.espeak_SetVoiceByName(b"en-us")
        lib.espeak_SetParameter(1, int(150 * speed), 0)  # rate (words per minute)
        lib.espeak_SetParameter(3, 30, 0)  # pitch, a bit low
        self.lib = lib

    def synth(self, text: str):
        self._chunks = []
        data = text.encode("utf-8") + b"\0"
        self.lib.espeak_Synth(data, len(data), 0, 1, 0, 0, None, None)
        self.lib.espeak_Synchronize()
        audio = np.concatenate(self._chunks) if self._chunks else np.zeros(1, dtype=np.int16)
        return audio.astype(np.float32) / 32768.0, self.sr


def get_tts(voice: str, speed: float, engine: str = "auto", cartesia_voice: str | None = None,
            cartesia_model: str = "sonic-3"):
    if engine == "cartesia" or (engine in ("auto", "kokoro") and cartesia_voice and os.environ.get("CARTESIA_API_KEY")):
        if not (cartesia_voice and os.environ.get("CARTESIA_API_KEY")):
            raise SystemExit("Cartesia needs `cartesia_voice:` in the story and a CARTESIA_API_KEY secret.")
        return CartesiaTTS(cartesia_voice, cartesia_model)
    have_kokoro = KOKORO_MODEL.exists() and KOKORO_VOICES.exists()
    if engine == "kokoro" or (engine == "auto" and have_kokoro):
        if not have_kokoro:
            raise SystemExit("Kokoro model files are missing. Run: python -m pipeline.download_models")
        return KokoroTTS(voice, speed)
    if engine == "auto":
        print("  ! Kokoro model not found, using the robotic eSpeak fallback voice.")
        print("    Run `python -m pipeline.download_models` for the real narrator.")
    return EspeakTTS(voice, speed)


def trim_silence(audio: np.ndarray, sr: int, threshold: float = 0.01, pad: float = 0.04) -> np.ndarray:
    loud = np.flatnonzero(np.abs(audio) > threshold)
    if loud.size == 0:
        return audio
    p = int(pad * sr)
    return audio[max(0, loud[0] - p): loud[-1] + p]
