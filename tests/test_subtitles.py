from subtitles import WordBoundary, format_timestamp, group_boundaries, write_srt


def wb(word, start, end):
    return WordBoundary(word=word, start=start, end=end)


def test_format_timestamp_rolls_hours_and_pads():
    assert format_timestamp(0) == "00:00:00,000"
    assert format_timestamp(3903.25) == "01:05:03,250"
    assert format_timestamp(78 * 60) == "01:18:00,000"


def test_groups_by_words_per_line():
    bounds = [wb("one", 0.0, 0.3), wb("two", 0.3, 0.6),
              wb("three", 0.6, 0.9), wb("four", 0.9, 1.2)]
    groups = group_boundaries(bounds, words_per_line=3)
    assert groups == [("one two three", 0.0, 0.9), ("four", 0.9, 1.2)]


def test_word_pop_mode_one_word_per_cue():
    bounds = [wb("hi", 0.0, 0.2), wb("there", 0.2, 0.5)]
    assert group_boundaries(bounds, words_per_line=1) == [
        ("hi", 0.0, 0.2), ("there", 0.2, 0.5)]


def test_sentence_end_breaks_line_early():
    bounds = [wb("Done.", 0.0, 0.4), wb("Next", 0.5, 0.8), wb("bit", 0.8, 1.0)]
    groups = group_boundaries(bounds, words_per_line=3)
    assert groups[0] == ("Done.", 0.0, 0.4)
    assert groups[1] == ("Next bit", 0.5, 1.0)


def test_long_line_breaks_on_max_chars():
    bounds = [wb("supercalifragilistic", 0.0, 1.0), wb("expialidocious", 1.0, 2.0)]
    groups = group_boundaries(bounds, words_per_line=5, max_line_chars=20)
    assert len(groups) == 2


def test_write_srt_produces_valid_blocks(tmp_path):
    out = tmp_path / "s.srt"
    write_srt([wb("hey", 0.0, 0.5), wb("you", 0.5, 1.0)], str(out), words_per_line=1)
    text = out.read_text(encoding="utf-8")
    assert text == ("1\n00:00:00,000 --> 00:00:00,500\nhey\n\n"
                    "2\n00:00:00,500 --> 00:00:01,000\nyou\n\n")
