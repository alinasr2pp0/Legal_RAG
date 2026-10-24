"""Generate the Grafana dashboard JSON (so it is reviewable, reproducible and consistent).

    python scripts/ops/build_grafana_dashboard.py          # writes monitoring/grafana/dashboards/...

The dashboard reads the metrics exported by ``rag/monitoring/exporter.py`` through Prometheus and uses a
``datasource`` variable, so it works both when provisioned and when imported by hand.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parents[2] / "monitoring/grafana/dashboards/civil_code_rag.json"
DS = {"type": "prometheus", "uid": "${datasource}"}
GREEN, YELLOW, ORANGE, RED, BLUE = "green", "#EAB839", "orange", "red", "blue"

_id = 0


def _next() -> int:
    global _id
    _id += 1
    return _id


def target(expr: str, legend: str = "", ref: str = "A", instant: bool = False) -> dict[str, Any]:
    t: dict[str, Any] = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t["instant"] = True
    return t


def steps(*pairs: tuple[str, float | None]) -> dict[str, Any]:
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in pairs]}


def row(title: str, y: int) -> dict[str, Any]:
    return {"id": _next(), "type": "row", "title": title, "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": []}


def stat(title: str, desc: str, expr: str, x: int, y: int, unit: str, th: dict[str, Any],
         w: int = 4, decimals: int | None = None, no_value: str = "—",
         graph: bool = True) -> dict[str, Any]:
    defaults: dict[str, Any] = {"unit": unit, "thresholds": th, "noValue": no_value,
                                "color": {"mode": "thresholds"}}
    if decimals is not None:
        defaults["decimals"] = decimals
    return {
        "id": _next(), "type": "stat", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"h": 4, "w": w, "x": x, "y": y},
        "targets": [target(expr)],
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": "background", "graphMode": "area" if graph else "none",
                    "textMode": "value", "justifyMode": "center", "orientation": "auto"},
    }


def ts(title: str, desc: str, targets: list[dict[str, Any]], x: int, y: int, w: int, unit: str,
       h: int = 8, th: dict[str, Any] | None = None, line_th: bool = False, stack: bool = False,
       min_: float | None = None, max_: float | None = None, bars: bool = False) -> dict[str, Any]:
    custom: dict[str, Any] = {
        "drawStyle": "bars" if bars else "line", "lineWidth": 2, "fillOpacity": 18 if not bars else 70,
        "gradientMode": "opacity", "showPoints": "never", "spanNulls": True,
        "stacking": {"mode": "normal" if stack else "none", "group": "A"},
        "thresholdsStyle": {"mode": "line" if line_th else "off"},
    }
    defaults: dict[str, Any] = {"unit": unit, "custom": custom, "color": {"mode": "palette-classic"}}
    if th:
        defaults["thresholds"] = th
    if min_ is not None:
        defaults["min"] = min_
    if max_ is not None:
        defaults["max"] = max_
    return {
        "id": _next(), "type": "timeseries", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"h": h, "w": w, "x": x, "y": y}, "targets": targets,
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"legend": {"displayMode": "table", "placement": "bottom",
                               "calcs": ["lastNotNull", "max"], "showLegend": True},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }


def bargauge(title: str, desc: str, expr: str, legend: str, x: int, y: int, w: int,
             th: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _next(), "type": "bargauge", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"h": 8, "w": w, "x": x, "y": y},
        "targets": [target(expr, legend, instant=True)],
        "fieldConfig": {"defaults": {"unit": "percentunit", "min": 0, "max": 1, "thresholds": th,
                                     "color": {"mode": "thresholds"}, "noValue": "لم يُشغَّل بعد"},
                        "overrides": []},
        "options": {"displayMode": "gradient", "orientation": "horizontal", "showUnfilled": True,
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
    }


def build() -> dict[str, Any]:
    q_rate = "sum(rate(rag_queries_total[$__rate_interval]))"
    lat = "histogram_quantile({q}, sum by (le) (rate(rag_query_latency_ms_bucket[$__rate_interval])))"
    crit_total = "sum(rate(rag_critic_verdicts_total[$__rate_interval]))"
    crit_pass = 'sum(rate(rag_critic_verdicts_total{verdict="passed"}[$__rate_interval]))'
    cache_hit = ('sum(rate(rag_cache_events_total{cache="answer",result="hit"}[$__rate_interval]))'
                 ' / clamp_min(sum(rate(rag_cache_events_total{cache="answer"}[$__rate_interval])), 1e-9)')
    good_high = steps((RED, None), (YELLOW, 0.8), (GREEN, 0.9))
    lat_th = steps((GREEN, None), (YELLOW, 3000), (RED, 8000))

    p: list[dict[str, Any]] = []
    y = 0
    p.append(row("نظرة عامة · Overview", y))
    y += 1
    p += [
        stat("الطلبات / ثانية", "معدل الأسئلة المُجابة (آخر 5 دقائق).", q_rate, 0, y, "reqps",
             steps((BLUE, None)), decimals=2),
        stat("إجمالي الأسئلة", "عدد الأسئلة خلال النطاق الزمني المعروض.",
             "sum(increase(rag_queries_total[$__range]))", 4, y, "none", steps((BLUE, None)),
             decimals=0, graph=False),
        stat("زمن الاستجابة p95", "يجب أن يبقى أقل من 8 ثوانٍ (تنبيه HighP95Latency).",
             lat.format(q=0.95), 8, y, "ms", lat_th, decimals=0),
        stat("نسبة نجاح المراجِع", "الإجابات التي اجتازت مراجعة الـ critic ÷ كل الأحكام.",
             f"{crit_pass} / clamp_min({crit_total}, 1e-9)", 12, y, "percentunit", good_high,
             decimals=1),
        stat("إصابة الكاش", "نسبة الأسئلة التي أُجيبت من الكاش.", cache_hit, 16, y,
             "percentunit", steps((BLUE, None)), decimals=1),
        stat("Faithfulness (RAGAS)", "آخر قيمة مُقاسة. التنبيه تحت 0.80. تظهر بعد تشغيل run_evaluation.",
             "rag_faithfulness_score", 20, y, "none",
             steps((RED, None), (YELLOW, 0.8), (GREEN, 0.9)), decimals=2,
             no_value="لم يُشغَّل بعد", graph=False),
    ]
    y += 4
    p.append(row("الحركة والزمن · Traffic & latency", y))
    y += 1
    p += [
        ts("الطلبات في الثانية", "كل الأسئلة، مقسومة على نوع الاستعلام عند توفره.",
           [target(q_rate, "كل الأسئلة"),
            target("sum(rate(rag_explicit_article_queries_total[$__rate_interval]))",
                   "سؤال عن مادة محددة", "B")], 0, y, 8, "reqps"),
        ts("زمن الاستجابة (p50 / p95 / p99)", "الخط الأحمر = حد التنبيه 8 ثوانٍ.",
           [target(lat.format(q=0.5), "p50"), target(lat.format(q=0.95), "p95", "B"),
            target(lat.format(q=0.99), "p99", "C")], 8, y, 16, "ms",
           th=steps((GREEN, None), (RED, 8000)), line_th=True, min_=0),
    ]
    y += 8
    p.append(row("جودة الإجابات والأمان · Answer quality & safety", y))
    y += 1
    p += [
        ts("أحكام المراجِع", "passed = اجتازت · failed = أُرفقت بتنبيه · refusal = رفض لعدم كفاية الأدلة.",
           [target("sum by (verdict) (rate(rag_critic_verdicts_total[$__rate_interval]))",
                   "{{verdict}}")], 0, y, 8, "reqps", stack=True, bars=True),
        ts("استناد الإجابة إلى النص (Grounding)", "p50 وp10؛ الخط = الحد الأدنى للمراجِع 0.55.",
           [target("histogram_quantile(0.5, sum by (le) (rate(rag_critic_grounding_bucket[$__rate_interval])))", "p50"),
            target("histogram_quantile(0.1, sum by (le) (rate(rag_critic_grounding_bucket[$__rate_interval])))", "p10", "B")],
           8, y, 8, "percentunit", th=steps((RED, None), (GREEN, 0.55)), line_th=True, min_=0, max_=1),
        ts("أحداث الحماية", "إعادة كتابة المسودة، اللجوء للويب، وإخفاء البيانات الشخصية.",
           [target("sum(rate(rag_answer_revisions_total[$__rate_interval]))", "إعادة كتابة"),
            target("sum(rate(rag_web_fallback_total[$__rate_interval]))", "لجوء للويب", "B"),
            target("sum by (kind) (rate(rag_pii_redactions_total[$__rate_interval]))", "PII: {{kind}}", "C")],
           16, y, 8, "ops"),
    ]
    y += 8
    p.append(row("RAGAS والانحراف · Evaluation & drift", y))
    y += 1
    p += [
        bargauge("مقاييس RAGAS (آخر تشغيل)", "faithfulness · answer_relevancy · context_precision · context_recall",
                 "rag_ragas_metric", "{{metric}}", 0, y, 8, steps((RED, None), (YELLOW, 0.7), (GREEN, 0.85))),
        ts("انحراف الـ embedding (MMD)", "الخط الأحمر = حد التنبيه 0.15.",
           [target("rag_embedding_drift_mmd", "MMD")], 8, y, 8, "none",
           th=steps((GREEN, None), (RED, 0.15)), line_th=True, min_=0),
        ts("انحراف cosine مقابل خط الأساس", "ارتفاعه المستمر يعني أن الأسئلة تبتعد عن بيانات البناء.",
           [target("rag_embedding_drift_cosine", "cosine"),
            target("rag_embedding_drift_delta{kind=\"mmd\",ref=\"median\"}", "Δ MMD عن الوسيط", "B")],
           16, y, 8, "none", min_=0),
    ]
    y += 8
    p.append(row("الكاش · Cache", y))
    y += 1
    p.append(ts("إصابة الكاش حسب النوع", "answer = الإجابات · embedding = تمثيلات الأسئلة.",
                [target('sum by (cache) (rate(rag_cache_events_total{result="hit"}[$__rate_interval]))'
                        ' / clamp_min(sum by (cache) (rate(rag_cache_events_total[$__rate_interval])), 1e-9)',
                        "{{cache}}")], 0, y, 24, "percentunit", h=7, min_=0, max_=1))

    return {
        "uid": "civil-code-rag",
        "title": "Egyptian Civil Code RAG — Monitoring",
        "description": "أداء وجودة وأمان نظام الأسئلة القانونية (مصدر البيانات: Prometheus ← /metrics).",
        "tags": ["rag", "legal", "arabic"],
        "timezone": "browser", "schemaVersion": 39, "version": 2, "editable": True,
        "graphTooltip": 1, "refresh": "15s", "time": {"from": "now-1h", "to": "now"},
        "timepicker": {"refresh_intervals": ["5s", "15s", "30s", "1m", "5m"]},
        "links": [{"title": "API docs", "type": "link", "url": "http://localhost:8000/docs",
                   "targetBlank": True}],
        "annotations": {"list": [{"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                                  "enable": True, "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
                                  "name": "Annotations & Alerts", "type": "dashboard"}]},
        "templating": {"list": [{"name": "datasource", "label": "Prometheus", "type": "datasource",
                                 "query": "prometheus", "current": {}, "hide": 0,
                                 "refresh": 1, "includeAll": False, "multi": False}]},
        "panels": p,
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
