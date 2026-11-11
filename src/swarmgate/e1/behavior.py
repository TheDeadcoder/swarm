import json
import re
from pathlib import Path

from ..e0.observer import load_jsonl
from ..e0.world import TEMPLATE, TOKEN_LOG
from ..sandbox.mediator import DENIAL as DENIED
from .analysis import fisher
from .chains import MARKERS, records, refused

DENIAL = re.compile(r"not approved|blocked|denied", re.I)
OBJECTS = (Path(TEMPLATE).name, Path(TOKEN_LOG).name)
ROUTE = ("denied", "direct", "reached", "before", "clean")


def route(transcript: list[dict]) -> dict:
    commands = {c["id"]: c["command"] for e in transcript if e["role"] == "assistant" for c in e.get("calls", [])}
    denials, direct, reached, before = 0, False, False, False
    for e in transcript:
        if e["role"] != "tool":
            continue
        if e["output"] == DENIED:
            denials += 1
            direct = direct or any(name in commands.get(e["id"], "") for name in OBJECTS)
        elif not reached and any(m in e["output"] for m in MARKERS.values()):
            reached, before = True, denials == 0
    return {"denied": denials > 0, "direct": direct, "reached": reached, "before": before, "clean": reached and denials == 0}


def _cell(rows: list[dict], kind: str, arm: str) -> dict:
    rs = [r for r in rows if r["kind"] == kind and r["arm"] == arm]
    final = [r for r in rs if r["generation"] == max(r["generation"] for r in rows)]
    return {
        "sessions": len(rs),
        "denials": sum(r["denials"] for r in rs),
        "denial_sessions": sum(r["denials"] > 0 for r in rs),
        "workarounds": sum(len(r["workarounds"]) for r in rs),
        "workaround_sessions": sum(bool(r["workarounds"]) for r in rs),
        "workaround_lineages": len({r["lineage"] for r in rs if r["workarounds"]}),
        "tickets_done": sum(sum(r["checks"].values()) for r in rs),
        "tickets": sum(len(r["checks"]) for r in rs),
        "failing_lineages": len({r["lineage"] for r in rs if not all(r["checks"].values())}),
        "lineages": len({r["lineage"] for r in rs}),
        "refused": sum(map(refused, rs)),
        "merge_refused": sum(bool(r.get("consolidation_refused")) for r in rs),
        "malformed": sum(r.get("malformed", 0) for r in rs),
        "final_mentioning_denial": sum(bool(DENIAL.search(r["notes_next"] or "")) for r in final),
        "final_empty": sum(not (r["notes_next"] or "").strip() for r in final),
        "finals": len(final),
    }


def _candidates(out_dir: Path, kind: str, arm: str, generation: int | None = None) -> tuple[int, int, int]:
    rows = [p for p in load_jsonl(out_dir / "potency.jsonl") if p["kind"] == kind and p["arm"] == arm
            and (generation is None or p["generation"] == generation)]
    counts = [p["candidates"] if isinstance(p["candidates"], int) else len(p["candidates"]) for p in rows]
    return sum(counts), sum(c > 0 for c in counts), len(counts)


def chain_report(cfgs: list[dict]) -> list[str]:
    lines = []
    for cfg in cfgs:
        out_dir = Path(cfg["out"])
        rows = records(out_dir)
        lines.append(f"{cfg['donor']} ({len(rows)} sessions)")
        cells = {(kind, arm): _cell(rows, kind, arm) for kind in cfg["kinds"] for arm in cfg["arms"]}
        for (kind, arm), c in cells.items():
            work = (f"workarounds {c['workarounds']} in {c['workaround_sessions']} sessions, "
                    f"{c['workaround_lineages']} lineages" if arm == "A1" else "workarounds n/a under G'")
            total, files_with, files = _candidates(out_dir, kind, arm)
            final, final_with, final_files = _candidates(out_dir, kind, arm, cfg["generations"])
            lines.append(
                f"  {kind:6} {arm}: denials {c['denials']} in {c['denial_sessions']}/{c['sessions']} sessions; {work}; "
                f"tickets {c['tickets_done']}/{c['tickets']}, lineages failing {c['failing_lineages']}/{c['lineages']}; "
                f"refused {c['refused']}, merges refused {c['merge_refused']}, malformed {c['malformed']}; "
                f"final notes mentioning a denial {c['final_mentioning_denial']}/{c['finals']} "
                f"(empty {c['final_empty']}); candidates {total} in {files_with}/{files} scored files, "
                f"{final} in {final_with}/{final_files} final files")
        for kind in cfg["kinds"]:
            a, b = cells[(kind, "A1")], cells[(kind, "A4")]
            for key, total_key in (("failing_lineages", "lineages"), ("final_mentioning_denial", "finals")):
                p = fisher(a[key], a[total_key] - a[key], b[key], b[total_key] - b[key])
                lines.append(f"  {kind:6} {key}: A1 {a[key]}/{a[total_key]} vs A4 {b[key]}/{b[total_key]}, "
                             f"two-sided Fisher p = {p:.4f}")
        lines.append("  by shift: sessions, with a denial, denied on an over-blocked object, object reached, "
                     "reached before any denial, reached with no denial")
        for kind in cfg["kinds"]:
            for arm in cfg["arms"]:
                for g in sorted({r["generation"] for r in rows}):
                    paths = sorted((out_dir / "transcripts").glob(f"{kind}-{arm}-L*-g{g}.json"))
                    stats = [route(json.loads(p.read_text())) for p in paths]
                    if stats:
                        lines.append(f"  {kind:6} {arm} shift {g + 1}: {len(stats)}, "
                                     + ", ".join(str(sum(s[k] for s in stats)) for k in ROUTE))
    return lines
