"""Master verification runner — Phases 1 through 5 + full pytest suite.

Run inside Docker:
    docker compose exec api python tests/run_all_verify.py

Options:
    --skip-locust     Skip the 60s Locust load test in phase5_verify
    --skip-pytest     Skip the pytest suite
    --phases 1,2,3    Run only selected phase verify scripts
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHASE_SCRIPTS = {
    1: "tests/phase1_verify.py",
    2: "tests/phase2_verify.py",
    3: "tests/phase3_verify.py",
    4: "tests/phase4_verify.py",
    5: "tests/phase5_verify.py",
    6: "tests/phase6_verify.py",
}


def run_script(name: str, path: str, extra_args: list[str] | None = None) -> int:
    cmd = [sys.executable, path] + (extra_args or [])
    print(f"\n{'=' * 60}")
    print(f"Running {name}")
    print(f"{'=' * 60}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all RouteMonitor verifications")
    parser.add_argument(
        "--phases",
        default="1,2,3,4,5,6",
        help="Comma-separated phase numbers to run (default: 1,2,3,4,5,6)",
    )
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--skip-locust", action="store_true")
    args = parser.parse_args()

    phases = [int(p.strip()) for p in args.phases.split(",") if p.strip()]
    failures: list[str] = []

    if not args.skip_pytest:
        print(f"\n{'=' * 60}")
        print("Running pytest (full suite)")
        print(f"{'=' * 60}")
        env = {**dict(**__import__("os").environ), "TESTING": "1"}
        rc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
            cwd=str(ROOT),
            env=env,
        ).returncode
        if rc != 0:
            failures.append(f"pytest (exit {rc})")
        else:
            print("  PASS  pytest full suite")

    for phase in phases:
        script = PHASE_SCRIPTS.get(phase)
        if not script:
            print(f"  SKIP  unknown phase {phase}")
            continue
        extra = []
        if phase == 5 and args.skip_locust:
            extra = ["--skip-locust"]
        rc = run_script(f"Phase {phase} verify", script, extra)
        if rc != 0:
            failures.append(f"phase{phase}_verify (exit {rc})")

    print(f"\n{'=' * 60}")
    print("Running complete endpoint sweep (live)")
    print(f"{'=' * 60}")
    rc = subprocess.run(
        [sys.executable, "tests/complete_verify.py"],
        cwd=str(ROOT),
    ).returncode
    if rc != 0:
        failures.append(f"complete_verify (exit {rc})")
    else:
        print("  PASS  complete_verify (all endpoints)")

    print(f"\n{'=' * 60}")
    print("MASTER VERIFICATION SUMMARY")
    print(f"{'=' * 60}")
    if failures:
        print(f"FAILED: {len(failures)} component(s)")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("ALL VERIFICATIONS PASSED (Phases 1–6 + pytest)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
