"""afi CLI — run a scenario on AS + audit, or audit an existing run.

A1: supports auditing an existing run_dir, and running AS from existing
AS config files then auditing (run-as). A2 adds run-afi-scenario <yaml>
using the scenario DSL (EW world-setting).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _audit_run(run_dir: str, out_html: str | None = None, full: bool = True):
    """Run the audit layer on an existing run_dir, write HTML report."""
    from afi.audit.load import load_spans
    from afi.audit.html_report import build_html
    spans = load_spans(run_dir)
    label = Path(run_dir).name
    out = out_html or f"afi_report_{label}.html"
    build_html([(label, run_dir)], out)
    print(f"[audit] {len(spans)} spans → {out}")
    return out


def _audit_runs(run_dirs: list, out_html: str | None = None):
    """Audit one or more runs; multiple -> cross-run comparison HTML."""
    from afi.audit.html_report import build_html
    labeled = [(Path(rd).name, rd) for rd in run_dirs]
    if out_html is None:
        out_html = f"afi_report_{'_vs_'.join(l for l, _ in labeled)}.html" if len(labeled) > 1 else f"afi_report_{labeled[0][0]}.html"
    build_html(labeled, out_html)
    print(f"[audit] {len(labeled)} run(s) → {out_html}")


def main():
    ap = argparse.ArgumentParser(prog="afi", description="afi-platform CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # audit an existing run
    p_audit = sub.add_parser("audit", help="audit run(s); multiple run_dirs -> cross-run comparison HTML")
    p_audit.add_argument("run_dirs", nargs="+", help="one or more run dirs")
    p_audit.add_argument("--out", default=None)

    # run AS from existing config + audit
    p_run = sub.add_parser("run-as", help="run AgentSociety from existing init_config+steps, then audit")
    p_run.add_argument("--as-config", required=True, help="AS init_config.json")
    p_run.add_argument("--as-steps", required=True, help="AS steps.yaml")
    p_run.add_argument("--run-dir", required=True, help="output run dir")
    p_run.add_argument("--model", default=None, help="override AS LLM model")
    p_run.add_argument("--as-home", default=None, help="AgentSociety checkout dir (sets checkout mode; unset → pip mode)")
    p_run.add_argument("--audit", action="store_true", help="audit after run")
    p_run.add_argument("--out", default=None, help="audit HTML output path")

    # run an EW-subset scenario YAML -> AS run -> audit (A2)
    p_ew = sub.add_parser("run-ew", help="build an EW-subset scenario -> AS run -> audit")
    p_ew.add_argument("scenario", help="EW-subset scenario YAML (e.g. scenarios/ew-subset.yaml)")
    p_ew.add_argument("--run-dir", required=True, help="output run dir")
    p_ew.add_argument("--model", default=None, help="override AS LLM model")
    p_ew.add_argument("--as-home", default=None, help="AgentSociety checkout dir")
    p_ew.add_argument("--preset", default=None, help="apply an EW-subset preset (cooperative/competitive/adversarial)")
    p_ew.add_argument(
        "--mode",
        choices=["contract", "autonomy"],
        default=None,
        help="scenario execution mode; contract runs explicit checkpoints only",
    )
    p_ew.add_argument(
        "--max-checkpoints",
        type=int,
        default=None,
        help="bound the number of explicit intervene checkpoints (smoke tests)",
    )
    p_ew.add_argument("--audit", action="store_true", help="audit after run (default: on)")
    p_ew.add_argument("--out", default=None, help="audit HTML output path")
    p_ew.set_defaults(audit=True)

    # AWI + runtime monitor on an existing run (A3)
    p_awi = sub.add_parser("awi", help="compute AWI 9 families + runtime alerts for a run")
    p_awi.add_argument("run_dir")
    p_awi.add_argument("--json", default=None, help="write AWI report JSON to this path")
    p_awi.add_argument("--no-runtime", action="store_true", help="skip runtime monitor alerts")

    # multi-model run + cross-model AWI comparison (A4)
    p_mm = sub.add_parser("multi-run", help="run one scenario across N models, compare AWI")
    p_mm.add_argument("scenario", help="scenario YAML (e.g. scenarios/ew_full.yaml)")
    p_mm.add_argument("--models", required=True, help="comma-separated LLM models (e.g. qwen-plus,qwen-max)")
    p_mm.add_argument("--run-root", required=True, help="output root; each model -> <root>/<model>/")
    p_mm.add_argument("--preset", default=None, help="apply an EW-subset preset")
    p_mm.add_argument("--as-home", default=None, help="AgentSociety checkout dir")
    p_mm.add_argument("--json", default=None, help="write comparison JSON to this path")

    # first-domino attribution + counterfactual rerun (phase-1 flagship)
    p_attr = sub.add_parser("attribution", help="localize first domino + optional counterfactual rerun")
    p_attr.add_argument("run_dir", help="existing run dir to attribute")
    p_attr.add_argument("--outcome", default="m1_collapse", help="outcome to localize (v0: m1_collapse)")
    p_attr.add_argument("--counterfactual", action="store_true", help="also run a counterfactual rerun on top-1 domino")
    p_attr.add_argument("--scenario", default=None, help="scenario YAML for counterfactual (e.g. scenarios/ew_full.yaml)")
    p_attr.add_argument("--model", default=None, help="LLM model for counterfactual rerun")
    p_attr.add_argument("--cf-run-dir", default=None, help="output run dir for counterfactual")
    p_attr.add_argument("--as-home", default=None, help="AgentSociety checkout dir")

    args = ap.parse_args()
    if args.cmd == "audit":
        _audit_runs(args.run_dirs, args.out)
    elif args.cmd == "run-as":
        _run_as(args)
    elif args.cmd == "run-ew":
        _run_ew(args)
    elif args.cmd == "awi":
        _run_awi(args)
    elif args.cmd == "multi-run":
        _run_multi(args)
    elif args.cmd == "attribution":
        _run_attribution(args)


def _run_as(args):
    """Use the AS adapter to run from existing AS config files, then audit."""
    import json
    from afi.backend.agentsociety import AgentSocietyAdapter, run_from_files

    adapter = AgentSocietyAdapter(as_home=args.as_home) if args.as_home else AgentSocietyAdapter()
    # A1 bridge: pass existing AS config + steps files directly to the adapter,
    # then audit the resulting run_dir.
    result = run_from_files(
        adapter,
        init_config_path=Path(args.as_config),
        steps_path=Path(args.as_steps),
        out_dir=Path(args.run_dir),
        model=args.model,
    )
    print(f"[run-as] done: {result.run_dir} ({result.steps} steps, {result.agent_count} agents)")
    if args.audit:
        _audit_run(str(result.run_dir), args.out)


def run_scenario_main():
    """entry point for `run-afi-scenario <yaml>` (A2). Delegates to `afi run-ew`."""
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("usage: run-afi-scenario <scenario.yaml> --run-dir <dir> [--model M] [--audit] [--out HTML]",
              file=sys.stderr)
        sys.exit(0)
    # treat the first positional as the scenario YAML for run-ew
    sys.argv = [sys.argv[0], "run-ew"] + args
    main()


def _run_ew(args):
    """Build an EW-subset scenario YAML -> AS run -> (optional) audit."""
    from pathlib import Path
    from afi.backend.agentsociety import AgentSocietyAdapter, run_from_files
    from afi.world.scenario import load_scenario, write_config

    run_dir = Path(args.run_dir)
    # write init_config + steps to a staging dir (NOT run_dir, which the
    # adapter wipes on run). Sibling "<run_dir>_config" keeps them for debugging.
    staging = run_dir.parent / (run_dir.name + "_config")

    scenario = load_scenario(args.scenario)
    if args.preset:
        from afi.world.scenario_presets import apply_preset
        scenario = apply_preset(scenario, args.preset)
        print(f"[run-ew] preset '{args.preset}' applied (initial_credits={scenario['world']['initial_credits']}, steps={len(scenario['steps'])})")
    if args.mode:
        scenario.setdefault("execution", {})["mode"] = args.mode
    if args.max_checkpoints is not None:
        scenario.setdefault("execution", {})["max_checkpoints"] = args.max_checkpoints
    cfg_path, steps_path = write_config(scenario, staging)
    print(f"[run-ew] scenario {args.scenario} -> {cfg_path}")

    adapter = AgentSocietyAdapter(as_home=args.as_home) if args.as_home else AgentSocietyAdapter()
    result = run_from_files(
        adapter,
        init_config_path=cfg_path,
        steps_path=steps_path,
        out_dir=run_dir,
        model=args.model,
    )
    print(f"[run-ew] done: {result.run_dir} ({result.steps} steps, {result.agent_count} agents)")
    if args.audit:
        _audit_run(str(result.run_dir), args.out)


def _run_awi(args):
    """Compute AWI 9 families + runtime alerts for a run_dir (A3)."""
    import json
    from dataclasses import asdict
    from afi.audit.awi import compute_awi, compute_awi_timeline, format_awi_report
    from afi.audit.runtime_monitor import run_monitor, format_alerts

    snap = compute_awi(args.run_dir)
    timeline = compute_awi_timeline(args.run_dir)
    alerts = [] if args.no_runtime else run_monitor(args.run_dir)
    label = Path(args.run_dir).name

    print(format_awi_report(snap, label))
    if not args.no_runtime:
        print()
        print(format_alerts(alerts))

    if args.json:
        payload = {
            "run": label,
            "awi": asdict(snap),
            "timeline_steps": len(timeline),
            "alerts": [asdict(a) for a in alerts],
        }
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n[awi] wrote {args.json}")


def _run_multi(args):
    """Run a scenario across N models + cross-model AWI comparison (A4)."""
    import json
    from afi.world.multi_model import run_multi_model, compare_runs, format_multi_report

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    results = run_multi_model(args.scenario, models, args.run_root, preset=args.preset, as_home=args.as_home)
    rep = compare_runs(results)
    print()
    print(format_multi_report(rep))

    if args.json:
        payload = {
            "models": models,
            "runs": results,
            "comparison": rep["comparison"],
            "stats": rep["stats"],
            "m1_vs_ew": rep["m1_vs_ew"],
        }
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n[multi] wrote {args.json}")


def _run_attribution(args):
    """First-domino localization + optional counterfactual rerun (phase-1)."""
    import json as _json
    from afi.audit.attribution import attribute, format_attribution

    rep = attribute(args.run_dir, args.outcome)
    print(format_attribution(rep))
    print(f"\n[attribution] wrote {args.run_dir}/attribution/{{event_graph,first_domino}}.json")

    if args.counterfactual:
        from afi.world.counterfactual import counterfactual_rerun, compare_m1
        cand = rep["localization"]["candidates"][0] if rep["localization"]["candidates"] else None
        if cand is None:
            print("[attribution] no domino candidate to run counterfactual on; skipping")
            return
        if not args.scenario or not args.model or not args.cf_run_dir:
            print("[attribution] --counterfactual requires --scenario, --model, --cf-run-dir")
            return
        print(f"\n[attribution] counterfactual rerun: domino agent {cand['agent_id']} {cand['kind']} "
              f"-> force recharge, model={args.model}")
        cf = counterfactual_rerun(
            args.scenario, cand, model=args.model,
            run_dir_out=args.cf_run_dir, as_home=args.as_home,
        )
        cmp = compare_m1(args.run_dir, cf["run_dir"])
        print(f"\n[attribution] counterfactual done: {cf['run_dir']}")
        print(f"  directive landed (recharge called in CF run): {cmp['directive_landed']}")
        print(f"  baseline alive@end={cmp['baseline_alive_at_end']}  cf alive@end={cmp['cf_alive_at_end']}")
        print(f"  averted/delayed: {cmp['averted_or_delayed']}")
        if cmp['cf_recharge_call_steps']:
            print(f"  cf recharge call steps: {cmp['cf_recharge_call_steps']}")
        out = Path(args.run_dir) / "attribution" / "counterfactual.json"
        out.write_text(_json.dumps(
            {"cf_run": cf, "comparison": {k: v for k, v in cmp.items() if k not in ("baseline_alive_curve", "cf_alive_curve")},
             "baseline_alive_curve": cmp["baseline_alive_curve"], "cf_alive_curve": cmp["cf_alive_curve"]},
            ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"  wrote {out}")


if __name__ == "__main__":
    main()
