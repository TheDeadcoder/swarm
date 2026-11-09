import argparse
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import probe


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m swarmgate.e1")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe")
    p.add_argument("--models", required=True)
    p.add_argument("--samples", type=int, default=3)
    p.add_argument("--roles", default="donor,attacker")
    p.add_argument("--observers-file", default="configs/observers.yaml")
    p.add_argument("--out", default="runs/probe/responses.jsonl")
    s = sub.add_parser("probe-summary")
    s.add_argument("--out", default="runs/probe/responses.jsonl")
    args = parser.parse_args()

    if args.cmd == "probe":
        specs = yaml.safe_load(Path(args.observers_file).read_text())
        chosen = {name: specs[name] for name in args.models.split(",")}
        print(json.dumps(probe.run(chosen, Path(args.out), args.samples, roles=tuple(args.roles.split(",")))))
    print("\n".join(probe.summary(Path(args.out))))


if __name__ == "__main__":
    main()
