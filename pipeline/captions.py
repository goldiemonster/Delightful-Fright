"""Shorts-style captions as an .ass subtitle file.

Plain white words, two or three at a time in the lower third, timed to the
narrator's actual words, the way the channel's Shorts caption. Words wrapped in
*asterisks* in the script are shown in muted lamp amber. The story title opens
the video as a quiet title card.
"""
import re

# ASS colours are &HAABBGGRR
WHITE = "&H00FFFFFF&"
ACTIVE = WHITE  # the spoken word isn't highlighted: calmer, like the channel
EMPHASIS = "&H004FA8D8&"  # muted lamp amber
GREY = "&H00B4B4B4&"


def _ts(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def words(text: str) -> list[tuple[str, bool]]:
    """(word, emphasised) pairs, honouring *multi word* emphasis."""
    out, emphasised = [], False
    for raw in text.split():
        starts, ends = raw.startswith(("*", "“*", "\"*")), raw.rstrip(".,!?;:\"'”…").endswith("*")
        if starts:
            emphasised = True
        out.append((raw.replace("*", "").replace("{", "(").replace("}", ")"), emphasised))
        if ends:
            emphasised = False
    return out


def strip_markup(text: str) -> str:
    return text.replace("*", "")


def _groups(items, max_words: int = 3, max_chars: int = 14):
    """Split a line's words into caption groups, breaking at punctuation."""
    group = []
    for idx, (word, emph) in enumerate(items):
        if group and (len(group) >= max_words or sum(len(w) for _, w, _ in group) + len(word) > max_chars):
            yield group
            group = []
        group.append((idx, word, emph))
        if re.search(r"[.!?…,;:—]['\"”’]?$", word):
            yield group
            group = []
    if group:
        yield group


def _esc(word: str) -> str:
    return word.upper().replace("\\", "")


def build_ass(lines, path, title: str | None = None, title_end: float = 0.0,
              font: str = "Anton", width: int = 1080, height: int = 1920):
    """lines: iterable of (text, [(start, end) per word])."""
    events = []
    if title:
        events.append(
            f"Dialogue: 1,{_ts(0)},{_ts(title_end)},Title,,0,0,0,,"
            r"{\fad(250,400)}" + f"{{\\c{GREY}\\fs50}}DELIGHTFUL FRIGHT\\N{{\\r}}{_esc(title)}"
        )
    for text, times in lines:
        items = words(text)
        for group in _groups(items):
            first, last = group[0][0], group[-1][0]
            g_start, g_end = times[first][0], times[last][1]
            for pos, (idx, _, _) in enumerate(group):
                # One event per word: the whole group shows, with the spoken word lit.
                w_start = g_start if pos == 0 else times[idx][0]
                w_end = g_end if pos == len(group) - 1 else times[group[pos + 1][0]][0]
                if w_end <= w_start:
                    continue
                body = " ".join(
                    f"{{\\c{EMPHASIS if e else ACTIVE if j == idx else WHITE}}}{_esc(w)}" for j, w, e in group
                )
                events.append(f"Dialogue: 0,{_ts(w_start)},{_ts(w_end)},Cap,,0,0,0,,{body}")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},84,{WHITE},{WHITE},&H00000000&,&H80000000&,0,0,0,0,100,100,2,0,1,4,2,2,90,90,560,1
Style: Title,{font},84,{WHITE},{WHITE},&H00000000&,&H80000000&,0,0,0,0,100,100,3,0,1,4,2,8,80,80,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events) + "\n")
