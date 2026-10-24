"""DL-based drift metric: compares the embedding distribution of recent
production queries against a stored baseline using Maximum Mean
Discrepancy (MMD) with an RBF kernel, plus a centroid cosine-shift
fallback. Either can be exported as the "≥1 drift metric" requirement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def _rbf_kernel(x: np.ndarray, y: np.ndarray, gamma: float) -> np.ndarray:
    x_sq = np.sum(x**2, axis=1).reshape(-1, 1)
    y_sq = np.sum(y**2, axis=1).reshape(1, -1)
    dists = x_sq + y_sq - 2 * x @ y.T
    return np.asarray(np.exp(-gamma * np.clip(dists, 0, None)))


def compute_mmd(baseline: np.ndarray, current: np.ndarray, gamma: float = 0.05) -> float:
    """Maximum Mean Discrepancy between two sets of embeddings. Higher = more drift."""
    k_xx = _rbf_kernel(baseline, baseline, gamma).mean()
    k_yy = _rbf_kernel(current, current, gamma).mean()
    k_xy = _rbf_kernel(baseline, current, gamma).mean()
    mmd_sq = k_xx + k_yy - 2 * k_xy
    return float(max(mmd_sq, 0.0) ** 0.5)


def compute_centroid_shift(baseline: np.ndarray, current: np.ndarray) -> float:
    """1 - cosine similarity between baseline centroid and current centroid."""
    baseline_centroid = baseline.mean(axis=0)
    current_centroid = current.mean(axis=0)
    cos_sim = np.dot(baseline_centroid, current_centroid) / (
        np.linalg.norm(baseline_centroid) * np.linalg.norm(current_centroid) + 1e-8
    )
    return float(1 - cos_sim)


def compute_cosine_drift(baseline: np.ndarray, current: np.ndarray) -> float:
    """Handbook-named metric: mean pairwise cosine distance between each
    current-batch embedding and the baseline centroid (distinct from
    compute_centroid_shift, which compares two centroids to each other).
    Returns the average 1-cosine_similarity across the current batch —
    a distribution-level view rather than a single point comparison."""
    baseline_centroid = baseline.mean(axis=0)
    baseline_norm = baseline_centroid / (np.linalg.norm(baseline_centroid) + 1e-8)

    current_norms = current / (np.linalg.norm(current, axis=1, keepdims=True) + 1e-8)
    cos_sims = current_norms @ baseline_norm
    return float(1 - cos_sims.mean())


class DriftDetector:
    def __init__(self, baseline_embeddings: np.ndarray, alert_threshold: float = 0.15) -> None:
        self.baseline = baseline_embeddings
        self.alert_threshold = alert_threshold

    def evaluate(self, current_embeddings: np.ndarray) -> dict[str, float | bool]:
        mmd = compute_mmd(self.baseline, current_embeddings)
        centroid_shift = compute_centroid_shift(self.baseline, current_embeddings)
        cosine_drift = compute_cosine_drift(self.baseline, current_embeddings)
        return {
            "mmd": mmd,
            "centroid_shift": centroid_shift,
            "cosine_drift": cosine_drift,
            "alert": mmd > self.alert_threshold,
        }


@dataclass
class DriftDelta:
    """Change of the drift scores relative to earlier runs (not only to the
    fixed baseline): a slow creep or a sudden jump both show up here."""

    mmd_delta_prev: float
    cosine_delta_prev: float
    mmd_delta_median: float
    cosine_delta_median: float
    alert: bool


class DriftHistory:
    """Append-only JSONL history of drift results; gives delta-vs-previous and
    delta-vs-rolling-median so the alert can fire on *movement*, which a single
    absolute threshold against a fixed baseline misses."""

    def __init__(self, path: str | Path, window: int = 7, delta_threshold: float = 0.05) -> None:
        self.path = Path(path)
        self.window = window
        self.delta_threshold = delta_threshold

    def _load(self) -> list[dict[str, float]]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def record(self, mmd: float, cosine_drift: float) -> DriftDelta:
        history = self._load()[-self.window :]
        if history:
            prev = history[-1]
            med_mmd = float(np.median([h["mmd"] for h in history]))
            med_cos = float(np.median([h["cosine_drift"] for h in history]))
            delta = DriftDelta(
                mmd_delta_prev=mmd - prev["mmd"],
                cosine_delta_prev=cosine_drift - prev["cosine_drift"],
                mmd_delta_median=mmd - med_mmd,
                cosine_delta_median=cosine_drift - med_cos,
                alert=False,
            )
            delta.alert = (
                abs(delta.mmd_delta_median) > self.delta_threshold
                or abs(delta.cosine_delta_median) > self.delta_threshold
            )
        else:  # first run: no history, nothing to compare with
            delta = DriftDelta(0.0, 0.0, 0.0, 0.0, False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"mmd": mmd, "cosine_drift": cosine_drift}) + "\n")
        return delta
