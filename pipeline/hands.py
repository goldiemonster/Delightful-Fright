"""Check painted hands for correct anatomy before a still is used.

AI painters often draw four or six fingers, fused fingers or a hand bent the wrong way. Every new
painting is shown to Claude, which counts the fingers on each visible hand; a painting that fails
is repainted with a new seed (see visuals.py), and QA fails if a bad hand survives every retry.

Needs ANTHROPIC_API_KEY. Without it nothing is checked and QA marks the check UNVERIFIED.
Verdicts are saved next to each cached image (<image>.hands.json), so each painting is checked once.
"""
import base64
import io
import json
import os
from pathlib import Path

import requests
from PIL import Image

MODEL = os.environ.get("HANDS_MODEL", "claude-sonnet-5-5")
PROMPT = (
    "You are checking an AI-generated painting for anatomically wrong hands before it is published.\n"
    "Look at every human hand that is visible, including partly visible ones, in shadow, or at the edges. "
    "For each, count the fingers including the thumb. A hand is wrong if it has more or fewer than five "
    "digits where all five should show, fused or melted fingers, an extra joint, a thumb on the wrong side, "
    "or a wrist or arm that bends impossibly. A hand that is plausibly partly hidden (fingers curled, "
    "behind an object, cut by the frame) is fine.\n"
    'Answer with JSON only: {"hands": <number of visible hands>, "ok": true|false, '
    '"problem": "<short description, or empty>"}'
)

REPORT: dict[str, dict] = {}  # image name -> verdict, for QA


def _ask(image: Path) -> dict:
    im = Image.open(image).convert("RGB")
    im.thumbnail((1024, 1024))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 200, "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(buf.getvalue()).decode()}},
            {"type": "text", "text": PROMPT},
        ]}]},
        timeout=120,
    )
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"])
    return json.loads(text[text.index("{"): text.rindex("}") + 1])


def check(image: Path) -> bool | None:
    """True if every visible hand is anatomically correct (or none shows), False if one isn't,
    None if it couldn't be checked."""
    sidecar = image.with_suffix(".hands.json")
    if sidecar.exists():
        verdict = json.loads(sidecar.read_text())
    elif not os.environ.get("ANTHROPIC_API_KEY"):
        verdict = {"ok": None, "problem": "not checked (no ANTHROPIC_API_KEY)"}
    else:
        try:
            verdict = _ask(image)
            sidecar.write_text(json.dumps(verdict))
        except (requests.RequestException, ValueError, KeyError) as e:
            verdict = {"ok": None, "problem": f"check failed: {e}"}
    REPORT[image.name] = verdict
    if verdict.get("ok") is False:
        print(f"  ! bad hand in {image.name}: {verdict.get('problem')}")
    return verdict.get("ok")
