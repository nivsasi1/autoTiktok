from dataclasses import dataclass


@dataclass
class WordBoundary:
    """One spoken word with real timings (seconds) from the TTS engine."""
    word: str
    start: float
    end: float


def group_boundaries(boundaries, words_per_line, max_line_chars=32):
    """Group word boundaries into caption cues: (words, start, end) where
    words keeps the per-word boundaries for karaoke timing."""
    groups, current = [], []

    def flush():
        if current:
            groups.append((current[:], current[0].start, current[-1].end))
            current.clear()

    for b in boundaries:
        line_len = sum(len(w.word) for w in current) + len(current) + len(b.word)
        if current and (len(current) >= words_per_line or line_len > max_line_chars):
            flush()
        current.append(b)
        if b.word and b.word[-1] in ".!?":  # end cue at sentence end
            flush()
    flush()
    return groups


def _ts(seconds: float) -> str:
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02}:{s:02}.{cs:02}"


def _sanitize(text: str) -> str:
    # braces would start ASS override tags; \N etc. can't appear in one word
    return text.replace("{", "(").replace("}", ")")


# PlayRes pins coordinates to the output size; styles reproduce the old
# force_style look (~7% height Arial bold, mid-center, soft black outline)
_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial,130,&H0000FFFF,&H00FFFFFF,&H80000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,0,5,60,60,60,1
Style: Text,Arial,130,&H00FFFFFF,&H00FFFFFF,&H80000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,0,5,60,60,60,1
Style: Hook,Arial,150,&H00FFFFFF,&H00FFFFFF,&H80000000,&H80000000,-1,0,0,0,100,100,0,0,1,8,0,8,60,60,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

HOOK_S = 2.5
HOOK_MAX_CHARS = 70


def _karaoke_text(words) -> str:
    """{\\kf<centisec>} per word: white until spoken, sweeps to yellow."""
    parts = []
    for i, w in enumerate(words):
        if i + 1 < len(words):
            dur = words[i + 1].start - w.start   # gap rides the current word
        else:
            dur = w.end - w.start
        parts.append(f"{{\\kf{max(int(round(dur * 100)), 1)}}}"
                     f"{_sanitize(w.word)}")
    return " ".join(parts)


def _hook_text(title: str) -> str:
    title = " ".join(title.split())
    if len(title) > HOOK_MAX_CHARS:
        cut = title[:HOOK_MAX_CHARS]
        idx = cut.rfind(" ")
        title = (cut[:idx] if idx > 0 else cut).rstrip() + "…"
    return _sanitize(title)


def write_ass(boundaries, path, words_per_line, max_line_chars=32,
              extra_cues=None, hook=None):
    """Karaoke captions + optional extras.

    extra_cues: [(text, start, end)] rendered in the plain-white Text style;
    inline overrides like {\\an8} pass through (that's how PART labels pin
    top-center). hook: title text shown 0->HOOK_S in the big Hook style.
    """
    events = []
    if hook:
        events.append((0.0, HOOK_S, "Hook",
                       "{\\fad(150,400)}" + _hook_text(hook)))
    for text, start, end in (extra_cues or []):
        events.append((start, end, "Text", text))
    for words, start, end in group_boundaries(boundaries, words_per_line,
                                              max_line_chars):
        events.append((start, end, "Karaoke", _karaoke_text(words)))
    events.sort(key=lambda e: e[0])
    with open(path, "w", encoding="utf-8") as f:
        f.write(_HEADER)
        for start, end, style, text in events:
            f.write(f"Dialogue: 0,{_ts(start)},{_ts(end)},{style},"
                    f",0,0,0,,{text}\n")
