"""Big, punchy word-group captions (the Shorts style) as an .ass subtitle file.

Words wrapped in *asterisks* in the script are shown in blood red.
Timing is estimated from each line's narration length, so no speech
recognition is needed.
"""
import re

RED = "&H001010D0&"  # ASS colours are &HAABBGGRR
WHITE = "&H00FFFFFF&"


def _ts(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _words(text: str):
    """Yield (word, emphasised) pairs, honouring *multi word* emphasis."""
    emphasised = False
    for raw in text.split():
        starts, ends = raw.startswith("*"), raw.rstrip(".,!?;:\"'”…").endswith("*")
        if starts:
            emphasised = True
        word = raw.replace("*", "").replace("{", "(").replace("}", ")")
        yield word, emphasised
        if ends:
            emphasised = False


def _groups(text: str, max_words: int = 3, max_chars: int = 16):
    group = []
    for word, emph in _words(text):
        if group and (len(group) >= max_words or sum(len(w) for w, _ in group) + len(word) > max_chars):
            yield group
            group = []
        group.append((word, emph))
        if re.search(r"[.!?…]$", word):  # end a group at sentence end
            yield group
            group = []
    if group:
        yield group


def strip_markup(text: str) -> str:
    return text.replace("*", "")


def build_ass(lines, path, font: str = "DejaVu Sans", width: int = 1080, height: int = 1920):
    """lines: iterable of (start_seconds, end_seconds, text)."""
    events = []
    for start, end, text in lines:
        groups = list(_groups(text))
        weights = [sum(len(w) for w, _ in g) + 2 for g in groups]
        total = sum(weights)
        t = start
        for g, wgt in zip(groups, weights):
            dur = (end - start) * wgt / total
            body = " ".join(f"{{\\c{RED if e else WHITE}}}{w}" for w, e in g)
            pop = r"{\fscx70\fscy70\t(0,90,\fscx100\fscy100)}"
            events.append(f"Dialogue: 0,{_ts(t)},{_ts(t + dur)},Cap,,0,0,0,,{pop}{body}")
            t += dur

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},96,{WHITE},{WHITE},&H00000000&,&H90000000&,-1,0,0,0,100,100,1,0,1,7,4,2,80,80,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
