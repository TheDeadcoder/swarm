import argparse
import json
import math
from pathlib import Path

import yaml
from dotenv import load_dotenv

from ..llm import list_models
from . import analysis, observer
from .ideal import Ideal
from .trials import build


def _load(path: str) -> tuple[dict, dict]:
    cfg = yaml.safe_load(Path(path).read_text())
    observers = yaml.safe_load(Path(cfg["observers_file"]).read_text())
    return cfg, observers


def _trials(cfg: dict, ideal: Ideal, run_dir: Path) -> list[dict]:
    path = run_dir / "trials.jsonl"
    if not path.exists():
        path.write_text("".join(json.dumps(t) + "\n" for t in build(cfg, ideal)))
    return observer.load_jsonl(path)


def _fmt(x: float) -> str:
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.3f}"


def _print(summary: list[dict], term: list[dict]) -> None:
    head = ("observer", "basis", "mode", "k", "logloss", "bacc", "attrib", "basis_acc", "bits")
    print("{:<24}{:<9}{:<14}{:>3}{:>9}{:>7}{:>8}{:>10}{:>7}".format(*head))
    for s in summary:
        if s["basis"] != "all" and s["k"] in (1, 4, 16) and s.get("parsed", 1) > 0:
            print("{:<24}{:<9}{:<14}{:>3}{:>9}{:>7}{:>8}{:>10}{:>7}".format(
                s["observer"], s["basis"], s["mode"], s["k"], _fmt(s["logloss"]), _fmt(s["bacc"]),
                _fmt(s["attribution"]), _fmt(s["class_acc"]), _fmt(s["bits"])))
    for t in term:
        print(f"termination delay={t['delay']} mode={t['mode']:<13} extra_bits={t['extra_bits']:.3f}")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m swarmgate.e0")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("trials", "ideal", "observe", "analyze", "models"):
        p = sub.add_parser(name)
        p.add_argument("--config", default="configs/e0.yaml")
        if name in ("observe", "models"):
            p.add_argument("--observer", required=True)
        if name == "observe":
            p.add_argument("--limit", type=int)
            p.add_argument("--retry-refused", action="store_true")
    args = parser.parse_args()
    cfg, observers = _load(args.config)

    if args.cmd == "models":
        print("\n".join(list_models(observers[args.observer])))
        return

    run_dir = Path("runs") / "e0" / cfg["name"]
    run_dir.mkdir(parents=True, exist_ok=True)
    ideal = Ideal(cfg["env_error_rate"], cfg["reveal_rate"])
    trials = _trials(cfg, ideal, run_dir)

    if args.cmd == "trials":
        print(f"{len(trials)} trials in {run_dir / 'trials.jsonl'}")
    elif args.cmd == "observe":
        spec = observers[args.observer]
        stats = observer.run(spec, args.observer, trials, run_dir, spec.get("workers", 4), args.limit,
                             retry_refused=args.retry_refused)
        print(json.dumps(stats))
        if stats["stopped"]:
            print(f"stopped early; see {run_dir / 'errors.jsonl'}. Re-run the same command to resume.")
    else:
        rows = analysis.score_ideal(ideal, trials)
        if args.cmd == "analyze":
            by_id = {t["trial_id"]: t for t in trials}
            responses = [r for r in observer.load_responses(run_dir / "responses.jsonl")
                         if r["trial_id"] in by_id and observer.in_scope(observers.get(r["observer"], {}), by_id[r["trial_id"]])]
            rows += analysis.score_observers(trials, responses)
        summary = analysis.aggregate(rows, cfg["modes"], cfg["bootstrap"], cfg["seed"])
        prefix = "ideal_" if args.cmd == "ideal" else ""
        analysis.write_csv(rows, run_dir / f"{prefix}scores.csv")
        analysis.write_csv(summary, run_dir / f"{prefix}summary.csv")
        term = analysis.termination(cfg, ideal, trials)
        analysis.write_csv(term, run_dir / "termination.csv")
        analysis.figures(summary, cfg["modes"], run_dir / "figures")
        _print(summary, term)
        for name in sorted({r["observer"] for r in rows if "parsed" in r}):
            rs = [r for r in rows if r["observer"] == name]
            print(f"{name}: parsed {sum(r['parsed'] for r in rs)}/{len(rs)}, refused {sum(r['refused'] for r in rs)}")


if __name__ == "__main__":
    main()
