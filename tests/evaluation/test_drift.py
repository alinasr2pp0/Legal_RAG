import numpy as np

from rag.evaluation.drift import DriftDetector, compute_mmd


def test_identical_distributions_have_near_zero_mmd():
    rng = np.random.default_rng(42)
    baseline = rng.normal(size=(50, 16))
    same_dist = rng.normal(size=(50, 16))
    assert compute_mmd(baseline, same_dist) < 0.2


def test_shifted_distribution_has_higher_mmd():
    rng = np.random.default_rng(42)
    baseline = rng.normal(loc=0.0, size=(50, 16))
    shifted = rng.normal(loc=5.0, size=(50, 16))
    assert compute_mmd(baseline, shifted) > compute_mmd(baseline, baseline)


def test_drift_detector_flags_alert():
    rng = np.random.default_rng(0)
    baseline = rng.normal(size=(50, 16))
    detector = DriftDetector(baseline_embeddings=baseline, alert_threshold=0.05)
    shifted = rng.normal(loc=10.0, size=(50, 16))
    result = detector.evaluate(shifted)
    assert result["alert"] is True


def test_cosine_drift_increases_with_larger_shift():
    from rag.evaluation.drift import compute_cosine_drift

    rng = np.random.default_rng(1)
    baseline = rng.normal(size=(50, 16))
    small_shift = baseline + rng.normal(scale=0.1, size=(50, 16))
    large_shift = rng.normal(loc=10.0, size=(50, 16))

    small_drift = compute_cosine_drift(baseline, small_shift)
    large_drift = compute_cosine_drift(baseline, large_shift)
    assert large_drift > small_drift


def test_drift_detector_reports_cosine_drift():
    rng = np.random.default_rng(2)
    baseline = rng.normal(size=(30, 8))
    detector = DriftDetector(baseline_embeddings=baseline)
    result = detector.evaluate(rng.normal(size=(30, 8)))
    assert "cosine_drift" in result


def test_drift_history_delta_and_alert(tmp_path):
    from rag.evaluation.drift import DriftHistory

    h = DriftHistory(tmp_path / "h.jsonl", window=5, delta_threshold=0.05)
    first = h.record(0.10, 0.20)
    assert first.alert is False and first.mmd_delta_prev == 0.0  # no history yet
    for _ in range(3):
        h.record(0.10, 0.20)
    steady = h.record(0.11, 0.21)
    assert steady.alert is False and abs(steady.mmd_delta_prev - 0.01) < 1e-9
    jump = h.record(0.30, 0.20)
    assert jump.alert is True and jump.mmd_delta_median > 0.15


def test_latency_histogram_buckets_cover_seconds_scale():
    """Buckets are milliseconds; the defaults (<=10) would make the 8 s p95 alert impossible."""
    from rag.monitoring.exporter import QUERY_LATENCY

    bounds = QUERY_LATENCY._upper_bounds  # noqa: SLF001 - prometheus_client has no public accessor
    assert 8000 in bounds and max(b for b in bounds if b != float("inf")) >= 30000
