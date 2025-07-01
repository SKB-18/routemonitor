"""Phase 6 portfolio verification — E2E smoke, docs, load test artifacts.

Run inside Docker:
    docker compose exec api python tests/phase6_verify.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PASS = FAIL = 0
ROOT = Path(__file__).resolve().parent.parent


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  {name}: {e}")


def test_docs_screenshots() -> None:
    print("\n=== 1. Dashboard screenshots (docs/) ===")
    for name in (
        "dashboard_screenshot.png",
        "route_timeline.png",
        "device_health.png",
        "anomaly_timeline.png",
        "correlation_matrix.png",
    ):
        check(name, lambda n=name: (ROOT / "docs" / n).stat().st_size > 1000)


def test_portfolio_files() -> None:
    print("\n=== 2. Portfolio files ===")
    for path in (
        "README.md",
        "PORTFOLIO.md",
        "DEMO_SCRIPT.md",
        "BLOG_POST.md",
        "CONTRIBUTING.md",
    ):
        check(path, lambda p=path: (ROOT / p).exists())


def test_github_username() -> None:
    print("\n=== 3. GitHub username ===")

    def no_placeholder():
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        assert "your-username" not in text
        assert "rohithachanta14" in text

    check("README uses rohithachanta14", no_placeholder)


def test_load_test_artifacts() -> None:
    print("\n=== 4. Load test artifacts ===")

    def stats_csv():
        p = ROOT / "tests" / "load" / "results_stats.csv"
        assert p.exists(), "Run Locust first"
        lines = p.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 2

    def zero_failures():
        import csv

        p = ROOT / "tests" / "load" / "results_stats.csv"
        rows = list(csv.DictReader(p.open()))
        agg = next(r for r in rows if r.get("Name") == "Aggregated")
        fails = int(float(agg.get("Failure Count", 0)))
        assert fails == 0, f"Expected 0 failures, got {fails}"

    check("results_stats.csv exists", stats_csv)
    check("Locust 0% failure rate", zero_failures)


def test_e2e_smoke() -> None:
    print("\n=== 5. E2E smoke script ===")

    def script_exists():
        assert (ROOT / "tests" / "phase6_e2e_smoke.py").exists()

    check("phase6_e2e_smoke.py present", script_exists)
    print(
        "       Run manually: docker compose exec api python tests/phase6_e2e_smoke.py"
    )


def main() -> int:
    print("=" * 60)
    print("RouteMonitor Phase 6 Portfolio Verification")
    print("=" * 60)
    test_docs_screenshots()
    test_portfolio_files()
    test_github_username()
    test_load_test_artifacts()
    test_e2e_smoke()
    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
