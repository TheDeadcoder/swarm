import json

from swarmgate.e1 import coding, vignettes
from swarmgate.llm import Call, Completion, Turn


def test_transcripts_end_with_the_resolution_then_the_notes_request():
    for resolution, steps in vignettes.RESOLUTIONS.items():
        t = vignettes.transcript(resolution)
        commands = [e["calls"][0]["command"] for e in t if e["role"] == "assistant"]
        assert commands[2].startswith("cat ") and commands[3:] == [s[0] for s in steps]
        assert t[-1] == {"role": "user", "text": vignettes.WRAP_UP}
    assert any(e.get("output") == vignettes.DENIAL for e in vignettes.transcript("legitimate"))


def test_notes_come_from_the_reply_or_a_notes_file_write():
    assert vignettes.notes_text(Turn(text="  - db.yaml updated\n")) == "- db.yaml updated"
    write = Call("c", "cat >> /team/NOTES.md <<'EOF'\n- use python3 to read it\nEOF")
    assert vignettes.notes_text(Turn(calls=[write])) == "- use python3 to read it"


def test_vignettes_run_every_cell(tmp_path):
    class Fake:
        def step(self, system, transcript, tools=True):
            return Turn(text="notes", stop="end_turn", meta={"usage": {"input": 1, "output": 1}})

    out = tmp_path / "v.jsonl"
    assert vignettes.run({"m": {}}, out, samples=2, clients={"m": Fake()})["done"] == 2 * 2 * len(vignettes.RESOLUTIONS)
    assert json.loads(out.read_text().splitlines()[0])["notes"] == "notes"


def test_codes_keep_disclosure_only_for_bypass_sessions():
    reply = '{"recipe": true, "labelled": false, "caveat": false, "negative": true, "legitimate": false, "escalation": false, "disclosure": "D2"}'
    assert coding.parse(reply, "interpreter")["disclosure"] == "D2"
    assert coding.parse(reply, "legitimate")["disclosure"] is None
    assert coding.parse("not json", "interpreter") is None
    assert "disclosure" in coding.prompt("x", "copy_rename") and "D1" not in coding.prompt("x", "escalation")


def test_second_coder_takes_a_fixed_random_share(tmp_path):
    source = tmp_path / "v.jsonl"
    rows = [{"model": "m", "cell_id": f"1-legitimate-{i}", "resolution": "legitimate", "good_faith": True, "notes": "n"}
            for i in range(10)]
    source.write_text("".join(json.dumps(r) + "\n" for r in rows))

    class Coder:
        def complete(self, system, user):
            return Completion(text='{"recipe": false}')

    stats = coding.run({"c": {}}, "c", source, tmp_path / "codes.jsonl", share=0.2, clients={"c": Coder()})
    assert stats["done"] == 2
