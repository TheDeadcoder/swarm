import argparse
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

from ..sandbox.container import Container
from . import analysis, calibration, chains, coding, potency, probe, vignettes


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m swarmgate.e1")
    parser.add_argument("--observers-file", default="configs/observers.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--models", required=True)
    p.add_argument("--samples", type=int, default=3)
    p.add_argument("--roles", default="donor,attacker")
    p.add_argument("--out", default="runs/probe/responses.jsonl")
    s = sub.add_parser("probe-summary")
    s.add_argument("--out", default="runs/probe/responses.jsonl")
    v = sub.add_parser("vignettes")
    v.add_argument("--models", required=True)
    v.add_argument("--samples", type=int, default=30)
    v.add_argument("--out", default="runs/vignettes/responses.jsonl")
    c = sub.add_parser("code")
    c.add_argument("--coder", required=True)
    c.add_argument("--source", default="runs/vignettes/responses.jsonl")
    c.add_argument("--out", required=True)
    c.add_argument("--share", type=float, default=1.0)
    r = sub.add_parser("vignette-report")
    r.add_argument("--run", default="runs/vignettes")
    for name in ("calibrate", "pilot", "chains", "score", "potency-report"):
        sub.add_parser(name).add_argument("--config", required=True)
    sub.choices["chains"].add_argument("--status", action="store_true")
    sub.choices["score"].add_argument("--generations", default="2,4")
    sub.choices["score"].add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if args.cmd == "vignette-report":
        print("\n".join(analysis.vignette_report(Path(args.run))))
        return
    specs = yaml.safe_load(Path(args.observers_file).read_text())
    cfg = yaml.safe_load(Path(args.config).read_text()) if "config" in args else {}
    out_dir = Path(cfg.get("out", "runs/e1"))

    if args.cmd == "calibrate":
        box = Container(f"sg-calibrate-{cfg['name']}")
        try:
            print("\n".join(calibration.calibrate(cfg, box)))
        finally:
            box.close()
        return
    if args.cmd == "pilot":
        print(json.dumps(chains.pilot(cfg, specs, out_dir)))
        print("\n".join(chains.pilot_report(cfg, out_dir, specs)))
        return
    if args.cmd == "chains":
        if not args.status:
            print(json.dumps(chains.run(cfg, specs, out_dir)))
        print("\n".join(chains.progress(cfg, out_dir, chains.model_prices(specs, cfg["donor"]))))
        return
    if args.cmd == "score":
        generations = tuple(int(g) for g in args.generations.split(","))
        print(json.dumps(potency.score_run(cfg, out_dir, generations, args.workers)))
        return
    if args.cmd == "potency-report":
        print("\n".join(analysis.potency_report(out_dir, cfg["generations"])))
        return

    if args.cmd in ("probe", "probe-summary"):
        if args.cmd == "probe":
            chosen = {name: specs[name] for name in args.models.split(",")}
            print(json.dumps(probe.run(chosen, Path(args.out), args.samples, roles=tuple(args.roles.split(",")))))
        print("\n".join(probe.summary(Path(args.out))))
    elif args.cmd == "vignettes":
        chosen = {name: specs[name] for name in args.models.split(",")}
        print(json.dumps(vignettes.run(chosen, Path(args.out), args.samples)))
    else:
        coder = {args.coder: specs[args.coder]}
        print(json.dumps(coding.run(coder, args.coder, Path(args.source), Path(args.out), args.share)))


if __name__ == "__main__":
    main()
