import split
from subtitles import WordBoundary


def wb(word, start, end):
    return WordBoundary(word=word, start=start, end=end)


def sentence_bounds():
    # 120s narration, sentence ends at 30s, 58s and 90s
    words, t = [], 0.0
    for end in (30.0, 58.0, 90.0, 119.0):
        while t < end - 2.0:
            words.append(wb("word", t, t + 1.8))
            t += 2.0
        words.append(wb("end.", t, end))
        t = end + 1.0
    return words


def test_cut_at_sentence_end_nearest_midpoint():
    bounds = sentence_bounds()
    cut, part1, part2 = split.split_boundaries(bounds, 120.0)
    assert 58.0 < cut < 60.0            # the 58s sentence end, mid-gap cut
    assert part1[-1].word == "end."
    assert part1[-1].end == 58.0


def test_part2_rebased_to_zero():
    bounds = sentence_bounds()
    cut, _, part2 = split.split_boundaries(bounds, 120.0)
    assert abs(part2[0].start - (bounds[len(bounds) - len(part2)].start - cut)) < 1e-9
    assert 0 <= part2[0].start < 2.0


def test_no_punctuation_falls_back_to_word_cut():
    bounds = [wb("word", t, t + 1.8) for t in range(0, 120, 2)]
    cut, part1, part2 = split.split_boundaries(bounds, 120.0)
    assert 55.0 < cut < 65.0
    assert len(part1) + len(part2) == len(bounds)


def test_sentence_ends_only_at_edges_use_word_cut_instead():
    # punctuation exists but only in the first/last 20% -> stub guard kicks in
    bounds = ([wb("start.", 0.0, 1.0)]
              + [wb("word", t, t + 1.8) for t in range(2, 118, 2)]
              + [wb("end.", 118.0, 119.0)])
    cut, part1, part2 = split.split_boundaries(bounds, 120.0)
    assert 24.0 <= cut <= 96.0
    assert part1 and part2


def test_unsplittable_returns_none():
    # a single word spanning the whole narration leaves nothing in the band
    assert split.split_boundaries([wb("aaa", 0.0, 120.0)], 120.0) is None


def test_label_cues_part1_has_to_be_continued():
    cues = split.label_cues(1, 60.0)
    texts = [c[0] for c in cues]
    assert r"{\an8}PART 1/2" in texts
    assert any("TO BE CONTINUED" in t for t in texts)
    tbc = next(c for c in cues if "TO BE CONTINUED" in c[0])
    assert tbc[2] == 60.0 and tbc[1] < 60.0


def test_label_cues_part2_only_labels():
    cues = split.label_cues(2, 55.0)
    assert len(cues) == 1
    assert cues[0][0] == r"{\an8}PART 2/2"
