from dataclasses import dataclass


@dataclass
class WordBoundary:
    """One spoken word with real timings (seconds) from the TTS engine."""
    word: str
    start: float
    end: float


def format_timestamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def group_boundaries(boundaries, words_per_line, max_line_chars=32):
    """Group word boundaries into caption cues: (text, start, end)."""
    groups, current = [], []

    def flush():
        if current:
            groups.append((" ".join(b.word for b in current),
                           current[0].start, current[-1].end))
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


def write_srt(boundaries, srt_path, words_per_line, max_line_chars=32):
    groups = group_boundaries(boundaries, words_per_line, max_line_chars)
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (text, start, end) in enumerate(groups, 1):
            f.write(f"{i}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{text}\n\n")
