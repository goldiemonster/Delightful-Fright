"""Download the free Kokoro narrator model (~340 MB, one time)."""
import urllib.request

from .tts import KOKORO_MODEL, KOKORO_VOICES, MODELS_DIR

BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"


def main():
    MODELS_DIR.mkdir(exist_ok=True)
    for path in (KOKORO_MODEL, KOKORO_VOICES):
        if path.exists():
            print(f"✓ {path.name} already downloaded")
            continue
        print(f"Downloading {path.name} …")
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(BASE + path.name, tmp)
        tmp.rename(path)
        print(f"✓ {path.name}")


if __name__ == "__main__":
    main()
