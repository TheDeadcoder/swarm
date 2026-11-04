import argparse
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import coding, probe, vignettes


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
    args = parser.parse_args()
    specs = yaml.safe_load(Path(args.observers_file).read_text())

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
