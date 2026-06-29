from app.generators.vocal_plan import build_vocal_plan, syllabify_word, syllable_at


def test_syllabify_multi_syllable_words():
    assert len(syllabify_word("shadow")) >= 2
    assert len(syllabify_word("rain")) == 1


def test_build_vocal_plan_counts_syllables_not_words():
    lyrics = """Verse:
I saw your shadow
Chorus:
Dancing in the rain"""
    plan = build_vocal_plan(
        lyrics,
        bpm=120,
        key="Am",
        duration_beats=32.0,
        scale=[0, 2, 4, 5, 7, 9, 11],
        root_hz=220.0,
        profile_name="pop",
    )
    assert plan.syllable_count() > 4
    assert len(plan.sections) == 2
    assert plan.sections[0].name == "verse"
    assert plan.sections[1].name == "chorus"


def test_longer_words_only_longer_with_more_syllables():
    lyrics = "cat shadow"
    plan = build_vocal_plan(
        lyrics,
        bpm=120,
        key=None,
        duration_beats=16.0,
        scale=[0, 2, 4, 5, 7, 9, 11],
        root_hz=261.63,
    )
    flat = plan.flat_syllables()
    cat_total = sum(s.beat_duration for s in flat if s.text == "cat")
    shadow_total = sum(s.beat_duration for s in flat if s.text in {"sha", "dow"})
    assert shadow_total > cat_total


def test_syllable_at_returns_active_syllable():
    plan = build_vocal_plan(
        "hello world",
        bpm=120,
        key=None,
        duration_beats=8.0,
        scale=[0, 2, 4, 5, 7, 9, 11],
        root_hz=261.63,
    )
    first = plan.flat_syllables()[0]
    hit = syllable_at(plan, first.beat_start + 0.01)
    assert hit is not None
    assert hit[0].text == first.text


def test_syllable_at_silent_during_line_rest():
    plan = build_vocal_plan(
        """Verse:
I walk alone beneath the city lights
Chorus:
We rise tonight""",
        bpm=118,
        key="C",
        duration_beats=48.0,
        scale=[0, 2, 4, 5, 7, 9, 11],
        root_hz=261.63,
        profile_name="pop",
    )
    for section in plan.sections:
        for line in section.lines:
            if line.rest_beats_after <= 0 or not line.syllables:
                continue
            last = line.syllables[-1]
            mid_rest = last.beat_start + last.beat_duration + line.rest_beats_after / 2
            assert syllable_at(plan, mid_rest) is None


def test_syllable_at_silent_after_plan_end():
    plan = build_vocal_plan(
        "hello world",
        bpm=120,
        key=None,
        duration_beats=16.0,
        scale=[0, 2, 4, 5, 7, 9, 11],
        root_hz=261.63,
    )
    assert syllable_at(plan, plan.vocal_end_beat() + 0.5) is None


def test_section_boundaries_preserved():
    lyrics = "Verse:\none two\nChorus:\nthree four"
    plan = build_vocal_plan(
        lyrics,
        bpm=100,
        key="C",
        duration_beats=24.0,
        scale=[0, 2, 4, 5, 7, 9, 11],
        root_hz=261.63,
    )
    assert [section.name for section in plan.sections] == ["verse", "chorus"]
    assert plan.sections[0].lines[0].text == "one two"
    assert plan.sections[1].lines[0].text == "three four"
