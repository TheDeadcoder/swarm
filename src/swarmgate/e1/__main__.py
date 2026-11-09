import argparse
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

from ..sandbox.container import Container
from . import analysis, battery, behavior, calibration, chains, coding, notes_coding, potency, probe, vignettes


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
    for name in ("battery", "battery-report"):
        b = sub.add_parser(name)
        b.add_argument("--configs", default="configs/e1.yaml,configs/e1-ow.yaml")
        b.add_argument("--out", default="runs/battery")
        b.add_argument("--anchors-only", action="store_true")
    sub.choices["battery"].add_argument("--reader", default="claude-sonnet-5")
    sub.choices["battery"].add_argument("--rpm", type=int)
    sub.choices["battery"].add_argument("--workers", type=int)
    sub.choices["battery"].add_argument("--exec-workers", type=int, default=8)
    sub.choices["battery"].add_argument("--api-key-env")
    sub.add_parser("chain-report").add_argument("--configs", default="configs/e1.yaml,configs/e1-ow.yaml")
    for name in ("notes-code", "notes-code-report"):
        n = sub.add_parser(name)
        n.add_argument("--configs", default="configs/e1.yaml,configs/e1-ow.yaml")
        n.add_argument("--out", default="runs/notes-coding")
    sub.choices["notes-code"].add_argument("--coder", required=True)
    sub.choices["notes-code"].add_argument("--share", type=float, default=1.0)
    sub.choices["notes-code"].add_argument("--donor")
    sub.choices["notes-code"].add_argument("--file")
    sub.choices["notes-code"].add_argument("--rpm", type=int)
    sub.choices["notes-code"].add_argument("--workers", type=int)
    sub.choices["notes-code"].add_argument("--api-key-env")
    for name in ("notes-code", "notes-code-report"):
        sub.choices[name].add_argument("--primary", default="codes-deepseek-v4-flash.jsonl")
        sub.choices[name].add_argument("--second", default="codes-second.jsonl")
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
    if args.cmd in ("battery", "battery-report"):
        cfgs = [yaml.safe_load(Path(p).read_text()) for p in args.configs.split(",")]
        srcs = battery.sources(cfgs, args.anchors_only)
        out = Path(args.out)
        responses, executions = out / "responses.jsonl", out / "executions.jsonl"
        if args.cmd == "battery":
            spec = dict(specs[args.reader])
            spec.update({k: v for k, v in (("rpm", args.rpm), ("workers", args.workers),
                                           ("api_key_env", args.api_key_env)) if v})
            print(json.dumps(battery.run({args.reader: spec}, srcs, responses)))
            print(json.dumps(battery.execute(srcs, responses, executions, args.exec_workers)))
        print("\n".join(battery.report(srcs, responses, executions)))
        return
    if args.cmd == "chain-report":
        cfgs = [yaml.safe_load(Path(p).read_text()) for p in args.configs.split(",")]
        print("\n".join(behavior.chain_report(cfgs)))
        return
    if args.cmd in ("notes-code", "notes-code-report"):
        cfgs = [yaml.safe_load(Path(p).read_text()) for p in args.configs.split(",")]
        out = Path(args.out)
        if args.cmd == "notes-code":
            spec = dict(specs[args.coder])
            spec.update({k: v for k, v in (("rpm", args.rpm), ("workers", args.workers),
                                           ("api_key_env", args.api_key_env)) if v})
            target = out / (args.file or f"codes-{args.coder}.jsonl")
            print(json.dumps(notes_coding.run({args.coder: spec}, cfgs, target, args.share, donor=args.donor)))
        print("\n".join(notes_coding.report(out / args.primary, out / args.second)))
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
