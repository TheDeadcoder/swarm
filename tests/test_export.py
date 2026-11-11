import csv
import json

from swarmgate.e1 import export


def test_tables_hold_one_row_per_session_code_and_trial_without_any_text(tmp_path):
    run, coding, bat, out = (tmp_path / name for name in ("run", "coding", "battery", "results"))
    for folder in (run, coding, bat):
        folder.mkdir()
    cell = {"kind": "syn", "arm": "A1", "lineage": 0}
    record = cell | {"generation": 0, "tasks": ["B1", "O1"], "checks": {"B1": True, "O1": False}, "calls": 5, "denials": 2,
                     "workarounds": ["template"], "turns": [{"refused": False}], "notes_next": "PRIVATE"}
    (run / "syn-A1-L00.jsonl").write_text(json.dumps(record) + "\n")
    scores = {o.id: False for o in export.OBJECTIVES}
    (run / "potency.jsonl").write_text(json.dumps(cell | {"generation": 1, "candidates": 2, "scores": scores}) + "\n")
    codes = {f: True for f in export.FLAGS}
    coded = cell | {"model": "x", "cell_id": "a", "donor": "d", "generation": 1, "codes": codes, "raw": "PRIVATE"}
    (coding / "codes-x.jsonl").write_text(json.dumps(coded) + "\n")
    reply = cell | {"model": "r", "cell_id": "t", "donor": "d", "objective": "S1", "sample": 0, "action": "command", "text": "PRIVATE"}
    (bat / "responses.jsonl").write_text(json.dumps(reply) + "\n")
    (bat / "executions.jsonl").write_text(json.dumps({"cell_id": "t", "allowed": True, "success": True}) + "\n")
    counts = export.tables([{"out": str(run), "donor": "d"}], out, [bat], coding)
    assert counts == {"sessions": 1, "potency": 1, "notes_codes": 1, "battery": 1}
    assert all("PRIVATE" not in p.read_text() for p in out.glob("*.csv"))
    with (out / "battery.csv").open() as f:
        row = next(csv.DictReader(f))
    assert row["reader"] == "r" and row["success"] == "1" and row["allowed"] == "1"
