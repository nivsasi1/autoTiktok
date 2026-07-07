"""Two-part splitter: narrations over the threshold become Part 1/2 + 2/2."""

from subtitles import WordBoundary

MIN_PART_FRACTION = 0.2   # neither part may be a stub of the story
LABEL_S = 3.0             # how long the PART x/2 label stays up


def split_boundaries(boundaries, narration):
    """Pick a cut near the middle, preferring sentence ends.

    Returns (cut_seconds, part1, part2) with part2 timings rebased to 0,
    or None when no cut leaves two decent parts (then render unsplit).
    """
    target = narration / 2
    lo, hi = narration * MIN_PART_FRACTION, narration * (1 - MIN_PART_FRACTION)

    def in_band(i):
        return lo <= boundaries[i].end <= hi

    candidates = [i for i in range(len(boundaries) - 1)
                  if boundaries[i].word[-1:] in ".!?" and in_band(i)]
    if not candidates:   # one giant sentence: cut between words instead
        candidates = [i for i in range(len(boundaries) - 1) if in_band(i)]
    if not candidates:
        return None
    best = min(candidates, key=lambda i: abs(boundaries[i].end - target))
    # cut in the silence between words so neither part clips speech
    cut = (boundaries[best].end + boundaries[best + 1].start) / 2
    part1 = boundaries[:best + 1]
    part2 = [WordBoundary(b.word, b.start - cut, b.end - cut)
             for b in boundaries[best + 1:]]
    return cut, part1, part2


def label_cues(part, duration):
    r"""Extra cues for write_ass; {\an8} pins them top-center, clear of
    the mid-screen word captions."""
    cues = [(r"{\an8}PART %d/2" % part, 0.2, 0.2 + LABEL_S)]
    if part == 1:
        cues.append((r"{\an8}TO BE CONTINUED…",
                     max(duration - LABEL_S, 0.0), duration))
    return cues
