"""Scoring — match findings against labels to compute precision/recall/F1.

Core logic:
1. Verifier filters labels whose seeds didn't fire (→ seed_dropped).
2. Match remaining labels to findings using category + agent_id + tick window.
3. Compute TP (matched), FP (unmatched findings), FN (unmatched labels).
4. Derive precision, recall, F1, latency_median, severity_mae.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import List, Optional

from eval.labels import Label
from eval.findings import Finding


# ── Matching logic ────────────────────────────────────────────────────────────

TICK_WINDOW = 2  # ±2 steps tolerance for temporal matching


def match(finding: Finding, label: Label) -> bool:
    """Check if a finding matches a label within tolerance.

    Rules:
    - category must match exactly
    - agent_id: if label.agent_id is None, any agent matches (system-level)
    - tick: |detected_at_tick - emerge_at_tick| <= TICK_WINDOW
    """
    if finding.category != label.category:
        return False
    if label.agent_id is not None and finding.agent_id != label.agent_id:
        return False
    if abs(finding.detected_at_tick - label.emerge_at_tick) > TICK_WINDOW:
        return False
    return True


# ── ScoreCard ─────────────────────────────────────────────────────────────────


@dataclass
class ScoreCard:
    """Scoring result for a single run.

    Attributes:
        precision: TP / (TP + FP). 1.0 if no findings at all.
        recall: TP / (TP + FN). 1.0 if no labels (natural scenario).
        f1: Harmonic mean of precision and recall.
        latency_median: Median (detected_tick - emerge_tick) for matched pairs.
        severity_mae: Mean |finding.severity - label.severity_expected| for matches.
        tp, fp, fn: Raw counts.
        seed_dropped: Number of labels removed by verifier.
        matched_pairs: List of (finding, label) pairs for inspection.
    """
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    latency_median: float = 0.0
    severity_mae: float = 0.0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    seed_dropped: int = 0
    matched_pairs: List[tuple] = field(default_factory=list)

    @property
    def total_findings(self) -> int:
        return self.tp + self.fp

    @property
    def total_labels(self) -> int:
        return self.tp + self.fn


# ── Scoring function ──────────────────────────────────────────────────────────


def score_run(
    findings: List[Finding],
    labels: List[Label],
    seed_dropped: int = 0,
) -> ScoreCard:
    """Score a single run: match findings to labels, compute metrics.

    Args:
        findings: Detected findings from detect_all().
        labels: Verified labels (after verifier removed seed_did_not_fire).
        seed_dropped: Count of labels dropped by verifier (for bookkeeping).

    Returns:
        ScoreCard with all metrics.
    """
    # Edge case: no labels (natural scenario)
    if not labels:
        return ScoreCard(
            precision=1.0 if not findings else 0.0,
            recall=1.0,  # vacuously true
            f1=1.0 if not findings else 0.0,
            tp=0, fp=len(findings), fn=0,
            seed_dropped=seed_dropped,
        )

    # Greedy matching: for each label, find best matching finding (closest tick)
    used_findings = set()
    matched_pairs = []
    latencies = []
    severity_diffs = []

    for label in labels:
        best_idx = None
        best_dist = float("inf")

        for i, finding in enumerate(findings):
            if i in used_findings:
                continue
            if match(finding, label):
                dist = abs(finding.detected_at_tick - label.emerge_at_tick)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i

        if best_idx is not None:
            used_findings.add(best_idx)
            matched_pairs.append((findings[best_idx], label))
            latencies.append(findings[best_idx].detected_at_tick - label.emerge_at_tick)
            severity_diffs.append(abs(findings[best_idx].severity - label.severity_expected))

    tp = len(matched_pairs)
    fp = len(findings) - tp
    fn = len(labels) - tp

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    latency_med = median(latencies) if latencies else 0.0
    severity_mae = sum(severity_diffs) / len(severity_diffs) if severity_diffs else 0.0

    return ScoreCard(
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        latency_median=round(latency_med, 2),
        severity_mae=round(severity_mae, 2),
        tp=tp,
        fp=fp,
        fn=fn,
        seed_dropped=seed_dropped,
        matched_pairs=matched_pairs,
    )


# ── Aggregation (for L2 multi-run) ───────────────────────────────────────────


@dataclass
class AggregatedScore:
    """Aggregated scores across multiple runs (same scenario, different seeds/models)."""
    scenario: str
    model: str
    n_runs: int
    precision_mean: float
    precision_ci95: float
    recall_mean: float
    recall_ci95: float
    f1_mean: float
    f1_ci95: float
    latency_mean: float
    severity_mae_mean: float
    seed_drop_rate: float  # fraction of labels dropped across all runs


def _ci95(values: List[float]) -> float:
    """Approximate 95% CI half-width (t-based for small n)."""
    n = len(values)
    if n <= 1:
        return 0.0
    import math
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    std = math.sqrt(variance)
    # t-value for 95% CI with n-1 df (approximate)
    t_vals = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 10: 2.23, 20: 2.09}
    t = t_vals.get(n - 1, 1.96)
    return t * std / math.sqrt(n)


def aggregate_scores(
    scores: List[ScoreCard],
    scenario: str,
    model: str,
) -> AggregatedScore:
    """Aggregate multiple ScoreCards into mean ± CI95."""
    n = len(scores)
    if n == 0:
        return AggregatedScore(scenario=scenario, model=model, n_runs=0,
                               precision_mean=0, precision_ci95=0,
                               recall_mean=0, recall_ci95=0,
                               f1_mean=0, f1_ci95=0,
                               latency_mean=0, severity_mae_mean=0, seed_drop_rate=0)

    precisions = [s.precision for s in scores]
    recalls = [s.recall for s in scores]
    f1s = [s.f1 for s in scores]
    latencies = [s.latency_median for s in scores]
    severities = [s.severity_mae for s in scores]
    total_labels = sum(s.total_labels + s.seed_dropped for s in scores)
    total_dropped = sum(s.seed_dropped for s in scores)

    return AggregatedScore(
        scenario=scenario,
        model=model,
        n_runs=n,
        precision_mean=round(sum(precisions) / n, 4),
        precision_ci95=round(_ci95(precisions), 4),
        recall_mean=round(sum(recalls) / n, 4),
        recall_ci95=round(_ci95(recalls), 4),
        f1_mean=round(sum(f1s) / n, 4),
        f1_ci95=round(_ci95(f1s), 4),
        latency_mean=round(sum(latencies) / n, 2),
        severity_mae_mean=round(sum(severities) / n, 2),
        seed_drop_rate=round(total_dropped / total_labels, 4) if total_labels else 0.0,
    )
