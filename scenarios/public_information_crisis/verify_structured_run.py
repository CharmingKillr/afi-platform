"""Verify a PIC-001 Contract Mode AgentSociety run.

The verifier treats the scenario YAML as the expected-call manifest and the
router's ``pic001_structured_call_log.jsonl`` as the observed execution log.
It does not infer success from ``pid.json`` alone: every expected call must be
present in order, use the expected tool and literal arguments, and return a
success status.  One JSON artifact is written per checkpoint so the result is
auditable without re-reading a long stdout log.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = Path(__file__).with_name("public_information_crisis.yaml")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from afi.world.scenario import load_scenario


def _extract_calls(instruction: str) -> list[str]:
    """Extract balanced ``Call tool(...)`` expressions from an instruction."""
    calls: list[str] = []
    for match in re.finditer(r"Call\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", instruction):
        start = match.start()
        opening = instruction.find("(", match.start())
        depth = 0
        quote: str | None = None
        escaped = False
        end = None
        for index in range(opening, len(instruction)):
            char = instruction[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                continue
            if char in {"'", '"'}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is not None:
            call = instruction[start:end].strip()
            if call not in calls:
                calls.append(call)
    return calls


def _parse_call(call: str) -> tuple[str, dict[str, Any]]:
    text = call.strip()
    if text.startswith("Call "):
        text = text[5:].strip()
    expression = ast.parse(text, mode="eval").body
    if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Name):
        raise ValueError(f"not a direct tool call: {call}")
    if any(keyword.arg is None for keyword in expression.keywords):
        raise ValueError(f"star arguments are not allowed: {call}")
    if expression.args:
        raise ValueError(f"Contract manifest requires keyword arguments: {call}")
    args = {
        str(keyword.arg): ast.literal_eval(keyword.value)
        for keyword in expression.keywords
    }
    return expression.func.id, args


def _checkpoint_id(step_index: int, instruction: str) -> str:
    headline = instruction.strip().splitlines()[0] if instruction.strip() else "checkpoint"
    headline = re.split(r"\bExecute\b", headline, maxsplit=1, flags=re.IGNORECASE)[0]
    headline = re.sub(r"^PIC-001\s*", "", headline, flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]+", "_", headline.lower()).strip("_")
    return f"pic001.step_{step_index}.{(slug or 'checkpoint')[:72].rstrip('_')}"


def expected_calls(scenario: dict) -> list[dict[str, Any]]:
    expected: list[dict[str, Any]] = []
    checkpoint_number = 0
    for step_index, step in enumerate(scenario.get("steps", [])):
        if step.get("type") != "intervene":
            continue
        checkpoint_number += 1
        checkpoint_id = _checkpoint_id(step_index, str(step.get("instruction", "")))
        for call_index, call in enumerate(_extract_calls(str(step.get("instruction", "")))):
            tool, args = _parse_call(call)
            expected.append({
                "checkpoint_number": checkpoint_number,
                "checkpoint_id": checkpoint_id,
                "step_index": step_index,
                "call_index": call_index,
                "call": call,
                "tool": tool,
                "args": args,
            })
    return expected


def _load_records(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "artifacts" / "pic001_structured_call_log.jsonl"
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def verify(run_dir: Path, output_dir: Path, allow_partial: bool = False) -> dict[str, Any]:
    scenario = load_scenario(SCENARIO)
    expected = expected_calls(scenario)
    observed = _load_records(run_dir)
    validation_expected = expected[: len(observed)] if allow_partial else expected
    comparisons: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []

    for index, item in enumerate(validation_expected):
        actual = observed[index] if index < len(observed) else None
        comparison = {
            "expected": item,
            "observed": actual,
            "status": "passed",
        }
        if actual is None:
            comparison["status"] = "missing"
        elif actual.get("tool") != item["tool"] or actual.get("args", {}) != item["args"]:
            comparison["status"] = "mismatch"
        elif actual.get("status") != "success":
            comparison["status"] = "failed"
        if comparison["status"] != "passed":
            mismatches.append(comparison)
        comparisons.append(comparison)

    unexpected = observed[len(expected):]
    output_dir.mkdir(parents=True, exist_ok=True)
    by_checkpoint: dict[str, list[dict[str, Any]]] = {}
    for comparison in comparisons:
        checkpoint_id = comparison["expected"]["checkpoint_id"]
        by_checkpoint.setdefault(checkpoint_id, []).append(comparison)

    checkpoint_reports = []
    for checkpoint_id, rows in by_checkpoint.items():
        passed = all(row["status"] == "passed" for row in rows)
        report = {
            "checkpoint_id": checkpoint_id,
            "status": "passed" if passed else "failed",
            "expected_call_count": len(rows),
            "observed_call_count": sum(row["observed"] is not None for row in rows),
            "calls": rows,
        }
        checkpoint_reports.append(report)
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", checkpoint_id)
        (output_dir / f"{safe_name}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    manifest_tools = set(scenario["world"]["ew_enabled_tools"])
    expected_tools = {item["tool"] for item in validation_expected}
    observed_tools = {record.get("tool") for record in observed}
    pid = {}
    pid_path = run_dir / "pid.json"
    if pid_path.is_file():
        pid = json.loads(pid_path.read_text(encoding="utf-8"))
    contract_passed = bool(
        validation_expected
        and len(observed) == len(validation_expected)
        and not mismatches
        and not unexpected
        and expected_tools.issubset(observed_tools)
    )
    result = {
        "run_type": "pic001_contract_mode_audit",
        "scenario_id": scenario["id"],
        "variant": scenario["variant"],
        "mode": "contract",
        "process_status": pid.get("status", "unknown"),
        "manifest_checkpoint_count": len({item["checkpoint_id"] for item in expected}),
        "validated_checkpoint_count": len(by_checkpoint),
        "passed_checkpoint_count": sum(report["status"] == "passed" for report in checkpoint_reports),
        "manifest_call_count": len(expected),
        "validated_call_count": len(validation_expected),
        "observed_call_count": len(observed),
        "failed_or_mismatched_calls": len(mismatches),
        "unexpected_call_count": len(unexpected),
        "public_tool_count": len(manifest_tools),
        "public_tool_count_validated": len(expected_tools),
        "public_tool_count_called": len(manifest_tools & observed_tools),
        "missing_public_tools": sorted(manifest_tools - observed_tools),
        "validation_scope": "partial_prefix" if allow_partial else "full_manifest",
        "scenario_status": (
            "passed" if contract_passed and not allow_partial
            else "passed_partial" if contract_passed and allow_partial
            else "failed"
        ),
        "checkpoints": checkpoint_reports,
        "mismatches": mismatches,
        "unexpected": unexpected,
    }
    (output_dir / "scenario_status.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="validate only the observed prefix (for bounded smoke tests)",
    )
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    output_dir = Path(args.output) if args.output else run_dir / "contract_audit"
    result = verify(run_dir, output_dir, allow_partial=args.allow_partial)
    print(json.dumps({key: value for key, value in result.items() if key not in {"checkpoints", "mismatches", "unexpected"}}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["scenario_status"] in {"passed", "passed_partial"} else 1)


if __name__ == "__main__":
    main()
