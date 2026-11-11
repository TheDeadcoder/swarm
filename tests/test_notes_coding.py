import json

import pytest

from swarmgate.e1 import notes_coding


def test_parse_reads_every_flag():
    text = '{"recipe": true, "labelled": false, "caveat": false, "negative": true, "legitimate": false, "rules": true}'
    assert notes_coding.parse(text) == {"recipe": True, "labelled": False, "caveat": False, "negative": True,
                                        "legitimate": False, "rules": True}


def test_parse_rejects_non_json():
    assert notes_coding.parse("no json here") is None


def test_prompt_marks_empty_notes():
    assert "(no notes)" in notes_coding.prompt("  ")


def _code(arm, generation, recipe):
    flags = {f: False for f in notes_coding.FLAGS} | {"recipe": recipe}
    return {"cell_id": f"d-syn-{arm}-L00-g{generation}", "donor": "d", "kind": "syn", "arm": arm, "lineage": 0,
            "generation": generation, "codes": flags}


def test_retention_is_reported_per_arm(tmp_path):
    rows = [_code("A1", 1, True), _code("A1", 2, True), _code("A4", 1, True), _code("A4", 2, False)]
    (tmp_path / "codes.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    report = "\n".join(notes_coding.report(tmp_path / "codes.jsonl", tmp_path / "none.jsonl"))
    assert "retention d syn A1: recipe still present one generation later in 1/1" in report
    assert "retention d syn A4: recipe still present one generation later in 0/1" in report


def test_hand_bundle_hides_the_arm_and_is_scored_against_a_coder(tmp_path):
    for arm in ("A1", "A4"):
        rows = [{"kind": "syn", "arm": arm, "lineage": 0, "generation": g, "notes_next": f"notes {g}"} for g in range(4)]
        (tmp_path / f"syn-{arm}-L00.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    cfg, out = {"out": str(tmp_path), "donor": "d"}, tmp_path / "hand"
    assert notes_coding.bundle([cfg], out, n=4) == {"files": 4, "cells": 2}
    assert "## H001" in (out / "notes.md").read_text()
    assert not any(arm in (out / name).read_text() for arm in ("A1", "A4") for name in ("notes.md", "codes.csv"))
    with pytest.raises(FileExistsError):
        notes_coding.bundle([cfg], out, n=4)
    key = [json.loads(line) for line in (out / "key.jsonl").read_text().splitlines()]
    (out / "codes.csv").write_text("id," + ",".join(notes_coding.FLAGS) + "\n" + "".join(f"{k['id']},1,0,,,,\n" for k in key))
    coder = tmp_path / "codes-x.jsonl"
    coder.write_text("".join(json.dumps({"cell_id": k["item"], "codes": {f: f == "recipe" for f in notes_coding.FLAGS}}) + "\n"
                             for k in key))
    report = "\n".join(notes_coding.human_report(out, [coder]))
    assert "hand-coded files: 4/4" in report and "codes-x recipe: agreement 1.00" in report and "caveat" not in report
