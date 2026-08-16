#!/usr/bin/env python3
"""Single launcher for the thesis evaluation suites."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = ROOT / "tests" / "evaluation"


@dataclass(frozen=True)
class Evaluation:
    script: str
    description: str
    arguments: tuple[str, ...] = ()
    supports_quick: bool = True
    quick_output: str | None = None


EVALUATIONS = {
    "path-tracer": Evaluation(
        "path_tracer/evaluate_path_tracer.py",
        "Section 5.1: light-transport and AOV validation",
        quick_output="5_1_path_tracer",
    ),
    "bsdf": Evaluation(
        "bsdf/evaluate_bsdf.py",
        "Section 5.2: Principled BSDF validation",
        quick_output="5_2_bsdf",
    ),
    "sampling": Evaluation(
        "sampling/evaluate_sampling.py",
        "Section 5.3: sampling, clamping and denoising",
        quick_output="5_3_sampling",
    ),
    "features": Evaluation(
        "features/evaluate_features.py",
        "Section 5.4: camera, material and visibility features",
        quick_output="5_4_features",
    ),
    "lego": Evaluation(
        "integration/evaluate_integration.py",
        "Section 5.5.1: Lego production-scene integration",
        ("--scene", "lego"),
    ),
    "kitchen": Evaluation(
        "integration/evaluate_integration.py",
        "Section 5.5.2: Country Kitchen integration",
        ("--scene", "kitchen"),
    ),
    "scale-failure": Evaluation(
        "scale_failure/evaluate_scale_failure.py",
        "Section 5.6: production-scale failure evidence audit",
        supports_quick=False,
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one or more thesis evaluations with consistent settings."
    )
    parser.add_argument(
        "targets", nargs="*", choices=(*EVALUATIONS, "all"),
        help="Evaluations to run. Use --list to inspect them.",
    )
    parser.add_argument("--list", action="store_true", help="List targets and exit.")
    parser.add_argument(
        "--full", action="store_true",
        help="Run canonical settings; the default uses reduced quick settings.",
    )
    parser.add_argument(
        "--smoke", action="store_true",
        help="Run low-cost AOV and production-asset checks.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without running them."
    )
    parser.add_argument(
        "--keep-going", action="store_true",
        help="Continue after a failed evaluation and report all failures.",
    )
    return parser.parse_args()


def selected_targets(args: argparse.Namespace) -> list[str]:
    if args.smoke:
        return ["path-tracer", "lego", "kitchen"]
    if not args.targets:
        raise ValueError("choose at least one target, or use --smoke/--list")
    if "all" in args.targets:
        return list(EVALUATIONS)
    return list(dict.fromkeys(args.targets))


def command_for(name: str, args: argparse.Namespace) -> list[str]:
    evaluation = EVALUATIONS[name]
    command = [
        sys.executable,
        str(EVALUATION_DIR / evaluation.script),
        *evaluation.arguments,
    ]
    if args.smoke:
        if name == "path-tracer":
            command.extend(
                (
                    "--quick", "--only", "aov", "--output",
                    str(ROOT / "outputs" / "quick" / evaluation.quick_output),
                )
            )
        else:
            command.extend(("--quick", "--only", "manifest"))
    elif not args.full and evaluation.supports_quick:
        command.append("--quick")
        if evaluation.quick_output:
            command.extend(
                ("--output", str(ROOT / "outputs" / "quick" / evaluation.quick_output))
            )
    return command


def main() -> int:
    args = parse_args()
    if args.list:
        print("Evaluation targets")
        for name, evaluation in EVALUATIONS.items():
            mode = "quick/full" if evaluation.supports_quick else "audit only"
            print(f"  {name:14} {mode:10} {evaluation.description}")
        return 0

    try:
        targets = selected_targets(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    total_started = time.perf_counter()
    for index, name in enumerate(targets, start=1):
        command = command_for(name, args)
        display = " ".join(command)
        print(f"\n[{index}/{len(targets)}] {name}\n  {display}", flush=True)
        if args.dry_run:
            continue
        started = time.perf_counter()
        result = subprocess.run(command, cwd=ROOT, check=False)
        elapsed = time.perf_counter() - started
        print(f"  {'PASS' if result.returncode == 0 else 'FAIL'} ({elapsed:.1f}s)")
        if result.returncode != 0:
            failures.append(name)
            if not args.keep_going:
                break

    elapsed = time.perf_counter() - total_started
    if failures:
        print(f"\nFailed: {', '.join(failures)} ({elapsed:.1f}s total)")
        return 1
    if not args.dry_run:
        print(f"\nAll selected evaluations passed ({elapsed:.1f}s total).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
