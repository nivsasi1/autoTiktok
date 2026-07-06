from subtitles import WordBoundary, group_boundaries, write_ass


def wb(word, start, end):
    return WordBoundary(word=word, start=start, end=end)


def texts(groups):
    return [" ".join(w.word for w in words) for words, _, _ in groups]


def test_groups_by_words_per_line():
    bounds = [wb("one", 0.0, 0.3), wb("two", 0.3, 0.6),
              wb("three", 0.6, 0.9), wb("four", 0.9, 1.2)]
    groups = group_boundaries(bounds, words_per_line=3)
    assert texts(groups) == ["one two three", "four"]
    assert (groups[0][1], groups[0][2]) == (0.0, 0.9)


def test_word_pop_mode_one_word_per_cue():
    bounds = [wb("hi", 0.0, 0.2), wb("there", 0.2, 0.5)]
    groups = group_boundaries(bounds, words_per_line=1)
    assert texts(groups) == ["hi", "there"]


def test_sentence_end_breaks_line_early():
    bounds = [wb("Done.", 0.0, 0.4), wb("Next", 0.5, 0.8), wb("bit", 0.8, 1.0)]
    groups = group_boundaries(bounds, words_per_line=3)
    assert texts(groups) == ["Done.", "Next bit"]


def test_long_line_breaks_on_max_chars():
    bounds = [wb("supercalifragilistic", 0.0, 1.0), wb("expialidocious", 1.0, 2.0)]
    assert len(group_boundaries(bounds, words_per_line=5, max_line_chars=20)) == 2


def ass(tmp_path, *args, **kw):
    out = tmp_path / "c.ass"
    write_ass(*args, str(out), **kw)
    return out.read_text(encoding="utf-8")


def test_write_ass_header_and_karaoke_timing(tmp_path):
    # gap between 'hey' start and 'you' start = 0.6s -> {\kf60}
    text = ass(tmp_path, [wb("hey", 0.0, 0.5), wb("you", 0.6, 1.0)],
               words_per_line=2)
    assert "PlayResX: 1080" in text and "PlayResY: 1920" in text
    assert "Style: Karaoke," in text
    assert ("Dialogue: 0,0:00:00.00,0:00:01.00,Karaoke,,0,0,0,,"
            r"{\kf60}hey {\kf40}you") in text


def test_write_ass_hook_trims_fades_and_sanitizes(tmp_path):
    long_title = "spooky " * 15 + "{end}"
    text = ass(tmp_path, [wb("hey", 0.0, 0.5)], words_per_line=1,
               hook=long_title)
    line = next(l for l in text.splitlines() if ",Hook," in l)
    assert line.startswith("Dialogue: 0,0:00:00.00,0:00:02.50,Hook,")
    assert r"{\fad(150,400)}" in line
    assert "{end}" not in line          # braces neutralized
    assert "…" in line                  # trimmed at a word boundary
    assert len(line.split(r"\fad(150,400)}")[1]) <= 72


def test_write_ass_no_hook_no_hook_event(tmp_path):
    text = ass(tmp_path, [wb("hey", 0.0, 0.5)], words_per_line=1)
    assert ",Hook," not in text


def test_write_ass_extra_cues_use_text_style_and_pass_overrides(tmp_path):
    text = ass(tmp_path, [wb("hey", 5.0, 5.5)], words_per_line=1,
               extra_cues=[(r"{\an8}PART 1/2", 0.2, 3.2)])
    line = next(l for l in text.splitlines() if "PART 1/2" in l)
    assert ",Text," in line
    assert r"{\an8}" in line            # override kept verbatim
    assert "0:00:00.20,0:00:03.20" in line
    # sorted: label event comes before the 5s word cue
    assert text.index("PART 1/2") < text.index(r"{\kf")


def test_write_ass_single_word_gets_full_duration_sweep(tmp_path):
    text = ass(tmp_path, [wb("alone", 1.0, 1.8)], words_per_line=1)
    assert r"{\kf80}alone" in text
