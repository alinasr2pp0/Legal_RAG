"""Validate the Prometheus / Grafana files without running either (used by CI).

Checks: YAML parses, alert + dashboard PromQL parses, dashboard panels do not overlap, every metric
a panel or alert uses is actually exported by ``rag/monitoring/exporter.py``.
Needs ``promql-parser`` for the PromQL syntax check (skipped with a notice when missing).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def exported_metrics() -> set[str]:
    from prometheus_client import generate_latest

    from rag.monitoring import exporter

    names = set()
    text = generate_latest(exporter.registry).decode()
    for line in text.splitlines():
        m = re.match(r"# TYPE (\S+) (\w+)", line)
        if m:
            base = m.group(1)
            names.add(base)
            if m.group(2) == "histogram":
                names.update({base + "_bucket", base + "_sum", base + "_count"})
            if m.group(2) == "counter":
                names.add(base if base.endswith("_total") else base + "_total")
    return names


def metrics_in(expr: str) -> set[str]:
    return set(re.findall(r"\brag_[a-z_]+\b", expr))


def main() -> int:
    errors: list[str] = []
    for f in [ROOT / "monitoring/prometheus.yml", ROOT / "monitoring/local/prometheus.yml",
              ROOT / "monitoring/alerts.yml",
              ROOT / "monitoring/grafana/provisioning/datasources/prometheus.yml",
              ROOT / "monitoring/grafana/provisioning/dashboards/dashboards.yml"]:
        try:
            yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{f.relative_to(ROOT)}: {exc}")

    dash = json.loads((ROOT / "monitoring/grafana/dashboards/civil_code_rag.json").read_text("utf-8"))
    alerts = yaml.safe_load((ROOT / "monitoring/alerts.yml").read_text("utf-8"))
    exprs = [t["expr"] for p in dash["panels"] for t in p.get("targets", [])]
    exprs += [r["expr"] for g in alerts["groups"] for r in g["rules"]]

    known = exported_metrics()
    for e in exprs:
        for name in metrics_in(e) - known:
            errors.append(f"metric {name!r} is not exported (expr: {e[:70]}...)")

    seen: dict[tuple[int, int], str] = {}
    for p in dash["panels"]:
        g = p["gridPos"]
        for x in range(g["x"], g["x"] + g["w"]):
            for y in range(g["y"], g["y"] + g["h"]):
                if (x, y) in seen:
                    errors.append(f"panels overlap: {p['title']!r} / {seen[(x, y)]!r}")
                seen[(x, y)] = p["title"]

    try:
        import promql_parser
    except ImportError:
        print("NOTICE: promql-parser not installed; skipping PromQL syntax check")
    else:
        for e in exprs:
            try:
                promql_parser.parse(e.replace("$__rate_interval", "5m").replace("$__range", "1h"))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"PromQL error in {e[:70]}...: {exc}")

    for err in errors:
        print("ERROR:", err)
    print(f"checked {len(exprs)} expressions, {len(dash['panels'])} panels: "
          f"{'FAILED' if errors else 'ok'}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
