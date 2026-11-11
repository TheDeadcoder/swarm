import csv
from pathlib import Path

from ..e0.observer import load_jsonl
from .chains import records, refused
from .notes_coding import FLAGS
from .potency import OBJECTIVES


def _write(path: Path, rows: list[dict]) -> int:
    if rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return len(rows)


def _latest(path: Path) -> list[dict]:
    return list({r["cell_id"]: r for r in load_jsonl(path)}.values())


def tables(cfgs: list[dict], out: Path, battery_dirs: list[Path], coding_dir: Path) -> dict:
    sessions, potency, codes, trials = [], [], [], []
    for cfg in cfgs:
        run = Path(cfg["out"])
        for r in records(run):
            sessions.append({
                "donor": cfg["donor"], "kind": r["kind"], "arm": r["arm"], "lineage": r["lineage"], "shift": r["generation"] + 1,
                "b_task": r["tasks"][0], "chore": r["tasks"][1], "tickets_done": sum(r["checks"].values()),
                "calls": r["calls"], "denials": r["denials"], "workarounds": " ".join(r["workarounds"]),
                "refused": int(refused(r)), "merge_refused": int(bool(r.get("consolidation_refused"))),
                "malformed": r.get("malformed", 0)})
        for p in load_jsonl(run / "potency.jsonl"):
            n = p["candidates"] if isinstance(p["candidates"], int) else len(p["candidates"])
            potency.append({"donor": cfg["donor"], "kind": p["kind"], "arm": p["arm"], "lineage": p["lineage"],
                            "shift": p["generation"], "candidates": n, **{o.id: int(p["scores"][o.id]) for o in OBJECTIVES}})
    for path in sorted(coding_dir.glob("codes-*.jsonl")):
        for r in _latest(path):
            if r.get("codes"):
                codes.append({"coder": r["model"], "file": path.stem, "donor": r["donor"], "kind": r["kind"], "arm": r["arm"],
                              "lineage": r["lineage"], "shift": r["generation"], **{f: int(r["codes"][f]) for f in FLAGS}})
    for folder in battery_dirs:
        runs = {r["cell_id"]: r for r in load_jsonl(folder / "executions.jsonl")}
        for r in _latest(folder / "responses.jsonl"):
            run = runs.get(r["cell_id"])
            trials.append({"reader": r["model"], "donor": r["donor"], "kind": r["kind"], "arm": r["arm"], "lineage": r["lineage"],
                           "objective": r["objective"], "sample": r["sample"], "reply": r["action"],
                           "allowed": int(run["allowed"]) if run else "", "success": int(bool(run and run["success"]))})
    return {"sessions": _write(out / "sessions.csv", sessions), "potency": _write(out / "potency.csv", potency),
            "notes_codes": _write(out / "notes_codes.csv", codes), "battery": _write(out / "battery.csv", trials)}
