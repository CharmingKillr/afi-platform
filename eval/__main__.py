"""eval CLI — python -m eval <subcommand> [options]

Subcommands:
  run-one   Run + score a single scenario with one model/seed
  grid      Run the full parameterized grid (L2)
  score     Score already-completed run directories (offline, no re-run)
  report    Generate HTML + CSV from an existing EvalReport JSON
  grid-dry  Print the run grid without executing anything

Examples:
  # Score existing b8_qwen run against governance_stagnation labels
  python -m eval score runs/b8_qwen_cooperative --scenario eval/scenarios/governance_stagnation.yaml

  # Run one scenario locally with Qwen2.5-7B
  python -m eval run-one --scenario eval/scenarios/single_agent_drift.yaml --model qwen2.5-7b --seed 0

  # Print the full grid (no execution)
  python -m eval grid-dry --models qwen2.5-7b gemini-2.5-flash --seeds 0 1 2

  # Run the full L1 grid (local model only, 1 seed)
  python -m eval grid --models qwen2.5-7b --seeds 0

  # Generate HTML + CSV from completed eval runs
  python -m eval report --out data/eval_scorecard
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root on path
_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))

from eval.grid import generate_grid, grid_summary, INJECTED_TEMPLATES
from eval.run_eval import (
    EvalReport,
    RunResult,
    run_eval,
    run_grid_offline,
    score_existing_run,
    print_report,
    export_csv,
)
from eval.report import generate_scorecard_html


# ── helpers ───────────────────────────────────────────────────────────────────


def _save_report(report: EvalReport, out_stem: str):
    """Save HTML + CSV + JSON from a report."""
    out = Path(out_stem)
    # out itself may be a file stem (no extension), create its parent dir
    out.parent.mkdir(parents=True, exist_ok=True)
    # Also ensure out as a dir doesn't conflict (if out is a dir not a stem)
    if out.is_dir():
        out = out / "scorecard"

    html_path = Path(str(out) + ".html")
    generate_scorecard_html(report, html_path)
    print(f"  HTML  → {html_path}")

    csv_path, agg_path = export_csv(report, Path(str(out) + ".csv"))
    print(f"  CSV   → {csv_path}")
    print(f"  AGG   → {agg_path}")

    # also dump raw JSON for reproducibility
    json_path = Path(str(out) + ".json")
    _dump_json(report, json_path)
    print(f"  JSON  → {json_path}")


def _dump_json(report: EvalReport, path: Path):
    """Serialize EvalReport to JSON (findings/labels not serialized, just scores)."""
    data = {
        "summary": report.summary,
        "results": [
            {
                "scenario": r.spec.scenario_name,
                "model": r.spec.model,
                "seed": r.spec.seed,
                "status": r.status,
                "error": r.error,
                "duration_sec": r.duration_sec,
                "delta_recall": r.delta_recall,
                "score": {
                    "precision": r.score.precision,
                    "recall": r.score.recall,
                    "f1": r.score.f1,
                    "latency_median": r.score.latency_median,
                    "severity_mae": r.score.severity_mae,
                    "tp": r.score.tp, "fp": r.score.fp, "fn": r.score.fn,
                    "seed_dropped": r.score.seed_dropped,
                } if r.score else None,
                "naive_score": {
                    "precision": r.naive_score.precision,
                    "recall": r.naive_score.recall,
                    "f1": r.naive_score.f1,
                } if r.naive_score else None,
                "n_findings": len(r.findings),
                "n_naive_findings": len(r.naive_findings),
            }
            for r in report.results
        ],
        "aggregated": [
            {
                "scenario": a.scenario, "model": a.model, "n_runs": a.n_runs,
                "precision_mean": a.precision_mean, "precision_ci95": a.precision_ci95,
                "recall_mean": a.recall_mean, "recall_ci95": a.recall_ci95,
                "f1_mean": a.f1_mean, "f1_ci95": a.f1_ci95,
                "latency_mean": a.latency_mean,
                "seed_drop_rate": a.seed_drop_rate,
            }
            for a in report.aggregated
        ],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── subcommands ───────────────────────────────────────────────────────────────


def cmd_run_one(args):
    """Run + score a single scenario."""
    scenario = Path(args.scenario)
    if not scenario.exists():
        print(f"ERROR: scenario not found: {scenario}", file=sys.stderr)
        sys.exit(1)

    print(f"Running: {scenario.stem}  model={args.model}  seed={args.seed}")
    report = run_eval(
        base_dir=_HERE,
        models=[args.model],
        seeds=[args.seed],
        scenarios=[scenario.stem],
        skip_existing=not args.rerun,
        dry_run=False,
    )
    print_report(report)

    if args.out:
        _save_report(report, args.out)


def cmd_grid(args):
    """Run the full parameterized grid."""
    models = args.models or ["qwen2.5-7b"]
    seeds = [int(s) for s in args.seeds] if args.seeds else [0, 1, 2]
    scenarios = args.scenarios or None

    grid = generate_grid(models=models, seeds=seeds, scenarios=scenarios)
    print(f"Grid: {grid_summary(grid)}")
    print(f"Executing {len(grid)} runs …\n")

    report = run_eval(
        base_dir=_HERE,
        models=models,
        seeds=seeds,
        scenarios=scenarios,
        skip_existing=not args.rerun,
        dry_run=False,
    )
    print_report(report)

    out_stem = args.out or str(_HERE / "data" / "eval_scorecard")
    _save_report(report, out_stem)
    print(f"\nDone. Scorecard saved to {out_stem}.*")


def cmd_score(args):
    """Score already-completed runs (offline)."""
    run_dirs = [Path(d) for d in args.run_dirs]

    if args.scenario:
        # Score specific run_dirs against a single scenario
        scenario_path = Path(args.scenario)
        results = []
        for rd in run_dirs:
            if not rd.is_dir():
                print(f"  SKIP (not a dir): {rd}")
                continue
            try:
                result = score_existing_run(rd, scenario_path)
                results.append(result)
                sc = result.score
                if sc:
                    print(f"  {rd.name}: P={sc.precision:.3f} R={sc.recall:.3f} "
                          f"F1={sc.f1:.3f} TP={sc.tp} FP={sc.fp} FN={sc.fn} "
                          f"Δrecall={result.delta_recall:+.3f}")
                else:
                    print(f"  {rd.name}: scored but no labels")
            except Exception as e:
                print(f"  {rd.name}: ERROR {e}")

        from dataclasses import field as dc_field
        report = EvalReport(results=results)
        if args.out:
            _save_report(report, args.out)
    else:
        # Scan all runs/eval/* for known scenarios
        report = run_grid_offline(_HERE)
        print_report(report)
        if args.out:
            _save_report(report, args.out)


def cmd_report(args):
    """Generate HTML + CSV from completed eval runs (offline)."""
    report = run_grid_offline(_HERE)
    out_stem = args.out or str(_HERE / "data" / "eval_scorecard")
    print_report(report)
    _save_report(report, out_stem)
    print(f"\nSaved to {out_stem}.*")


def cmd_grid_dry(args):
    """Print the run grid without executing anything."""
    models = args.models or ["qwen2.5-7b", "gemini-2.5-flash"]
    seeds = [int(s) for s in args.seeds] if args.seeds else [0, 1, 2]
    grid = generate_grid(models=models, seeds=seeds)
    summary = grid_summary(grid)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nTotal: {summary['total_runs']} runs")
    print(f"  {summary['injected_runs']} injected  +  {summary['natural_runs']} natural")
    print()
    for spec in grid:
        print(f"  [{spec.scenario_name:28s}] model={spec.model:20s} seed={spec.seed}  → {spec.run_dir}")


# ── main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="python -m eval",
        description="AI Governance Lab Eval Suite CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run-one
    p = sub.add_parser("run-one", help="Run + score a single scenario")
    p.add_argument("--scenario", required=True, help="Path to scenario YAML")
    p.add_argument("--model", default="qwen2.5-7b")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", help="Output stem for HTML/CSV/JSON")
    p.add_argument("--rerun", action="store_true", help="Force re-run even if run_dir exists")

    # grid
    p = sub.add_parser("grid", help="Run the full parameterized grid (L2)")
    p.add_argument("--models", nargs="+", default=None)
    p.add_argument("--seeds", nargs="+", default=None)
    p.add_argument("--scenarios", nargs="+", default=None)
    p.add_argument("--out", help="Output stem for scorecard files")
    p.add_argument("--rerun", action="store_true")

    # score
    p = sub.add_parser("score", help="Score completed run directories offline")
    p.add_argument("run_dirs", nargs="*", help="run_dir paths to score")
    p.add_argument("--scenario", help="Scenario YAML to score against")
    p.add_argument("--out", help="Output stem for scorecard files")

    # report
    p = sub.add_parser("report", help="Generate HTML+CSV from all eval runs")
    p.add_argument("--out", help="Output stem (default: data/eval_scorecard)")

    # grid-dry
    p = sub.add_parser("grid-dry", help="Print grid without running")
    p.add_argument("--models", nargs="+", default=None)
    p.add_argument("--seeds", nargs="+", default=None)

    args = parser.parse_args()

    dispatch = {
        "run-one": cmd_run_one,
        "grid": cmd_grid,
        "score": cmd_score,
        "report": cmd_report,
        "grid-dry": cmd_grid_dry,
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
