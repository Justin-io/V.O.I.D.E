"""Command-line interface for V.O.I.D.E. 2.0."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service import generate_demo, run_replay
from .simulator import write_simulation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="voide2", description="Industrial digital twin and predictive replay")
    sub = parser.add_subparsers(dest="command", required=True)
    sim = sub.add_parser("simulate", help="generate deterministic synthetic telemetry")
    sim.add_argument("--out", default="artifacts/demo")
    sim.add_argument("--assets", type=int, default=4)
    sim.add_argument("--hours", type=int, default=240)
    sim.add_argument("--interval-minutes", type=int, default=10)
    sim.add_argument("--seed", type=int, default=20261112)
    replay = sub.add_parser("replay", help="validate and replay a telemetry CSV")
    replay.add_argument("csv")
    replay.add_argument("--out", default="artifacts/replay")
    replay.add_argument("--seed", type=int, default=42)
    demo = sub.add_parser("demo", help="run simulator, replay and benchmark end-to-end")
    demo.add_argument("--out", default="artifacts/demo")
    demo.add_argument("--seed", type=int, default=20261112)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "simulate":
        telemetry, truth = write_simulation(
            args.out,
            assets=args.assets,
            hours=args.hours,
            interval_minutes=args.interval_minutes,
            seed=args.seed,
        )
        print(json.dumps({"telemetry": str(telemetry), "ground_truth": str(truth)}, indent=2))
    elif args.command == "replay":
        result = run_replay(args.csv, benchmark_dir=args.out, seed=args.seed)
        print(json.dumps(result, indent=2))
    elif args.command == "demo":
        print(json.dumps(generate_demo(args.out, seed=args.seed), indent=2))


if __name__ == "__main__":
    main()
