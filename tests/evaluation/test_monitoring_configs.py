import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "ops" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_committed_dashboard_matches_generator():
    """Regenerate with scripts/ops/build_grafana_dashboard.py whenever the script changes."""
    import json

    built = _load("build_grafana_dashboard").build()
    committed = json.loads(
        (ROOT / "monitoring/grafana/dashboards/civil_code_rag.json").read_text(encoding="utf-8")
    )
    assert built == committed


def test_monitoring_configs_are_valid_and_use_exported_metrics():
    assert _load("check_monitoring_configs").main() == 0
