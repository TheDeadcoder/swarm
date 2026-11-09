from swarmgate.e1 import notes_coding


def test_parse_reads_every_flag():
    text = '{"recipe": true, "labelled": false, "caveat": false, "negative": true, "legitimate": false, "rules": true}'
    assert notes_coding.parse(text) == {"recipe": True, "labelled": False, "caveat": False, "negative": True,
                                        "legitimate": False, "rules": True}


def test_parse_rejects_non_json():
    assert notes_coding.parse("no json here") is None


def test_prompt_marks_empty_notes():
    assert "(no notes)" in notes_coding.prompt("  ")
