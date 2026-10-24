# دليل التشغيل الكامل (Windows، بدون Docker)

المنافذ والشاشات حسب الإعدادات الافتراضية في المشروع. ما لم يُجرَّب هنا (لغياب Ollama والنماذج وDocker وGrafana) مذكور في آخر الملف.

## 1) خريطة المنافذ

| المنفذ | الخدمة | يُشغَّل بـ | الرابط | مطلوب؟ |
|---|---|---|---|---|
| 11434 | Ollama (النموذج اللغوي) | تطبيق Ollama | http://localhost:11434 | نعم |
| 8000 | الخدمة (FastAPI) + الواجهة | `uvicorn` | http://localhost:8000 | نعم |
| 8000/docs | Swagger لكل الـAPI | مع الخدمة | http://localhost:8000/docs | تلقائي |
| 8000/metrics | أرقام Prometheus | مع الخدمة | http://localhost:8000/metrics | تلقائي |
| 9090 | Prometheus | `prometheus.exe` | http://localhost:9090 | للمراقبة |
| 3000 | Grafana | `grafana-server.exe` | http://localhost:3000 | للمراقبة |
| 9091 | Pushgateway (نتائج RAGAS والـdrift) | `pushgateway.exe` | http://localhost:9091 | اختياري |
| 5000 | MLflow UI | `mlflow ui` | http://localhost:5000 | اختياري |
| 8089 | Locust UI (اختبار الحمل) | `locust` | http://localhost:8089 | اختياري |
| 8001 | الخادم الوهمي لاختبار الحمل | `loadtest_server_stub.py` | http://localhost:8001 | اختياري |
| (بدون منفذ) | Qdrant (مضمّن في `data/qdrant`) | يعمل داخل الخدمة | - | تلقائي |
| 6333 | Qdrant كخادم (Docker فقط) | compose | - | لا تحتاجه |

الإعداد الافتراضي محلي: لا يحتاج مفاتيح Voyage أو Tavily، كما يُعطّل التتبع الخارجي.

## 2) التهيئة لمرة واحدة

```powershell
cd egyptian-civil-code-rag
python -m venv .venv ; .venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

في `.env`:
```
PROVIDER_PROFILE=local
LOCAL_ONLY=true
EMBEDDING_MODEL=D:/AI-Models/multilingual-e5-small
HF_OFFLINE=true
LLM_MODEL_PRIMARY=qwen2.5:3b
RERANKER_ENABLED=false
WEB_SEARCH_ENABLED=false
```
النموذج المحدد في `EMBEDDING_MODEL` يجب أن يكون موجودًا محليًا.

Ollama من مجلدك:
```powershell
setx OLLAMA_MODELS "D:\AI-Models\Ollama"
```
أعد تشغيل Ollama من الـTray ثم `ollama list` يجب أن يُظهر `qwen2.5:3b`.

## 3) بناء الفهرس (مرة، وعند تغيّر البيانات)
```powershell
python scripts/data/build_index.py --input data/serving/chunks.json
python scripts/ops/check_local_stack.py
```

## 4) التشغيل اليومي

| الترتيب | الأمر | يفتح |
|---|---|---|
| 1 | Ollama شغّال في الخلفية | - |
| 2 | `uvicorn api.main:app --app-dir src --port 8000` | الواجهة |
| 3 | (مراقبة) `prometheus.exe --config.file=<المشروع>\monitoring\local\prometheus.yml` | :9090 |
| 4 | (مراقبة) `bin\grafana-server.exe` | :3000 |

فحص الجاهزية: `http://localhost:8000/ready` يجب أن يرد 200. إن ردّ 503 فالنص يذكر الناقص (Ollama أو الفهرس أو النموذج).

## 5) شاشات الواجهة (`http://localhost:8000`)

| الشاشة | ما تفعله |
|---|---|
| **المحادثة** | اكتب سؤالًا أو اختر سؤالًا مقترحًا. تظهر الإجابة مبثوثة، ثم شريط التحقق (نجح المراجِع أم لا + نسبة الاستناد)، ثم شارات المواد المرجعية. اضغط شارة لتفتح نص المادة كاملًا. أزرار: محادثة جديدة، تصدير، مسح السجل، 👍/👎 |
| **القضية** | أنشئ قضية وارفع PDF نصيًا أو Word أو TXT أو Markdown؛ تُستخدم المستندات كوقائع في الإجابة ولا تصبح استشهادًا قانونيًا |
| **السجل** | الأسئلة السابقة، ويمكن فتحها مجددًا |
| **المتابعة** | لوحة مؤشرات حية من `/stats`: الطلبات والزمن والاستناد والرضا وأكثر المواد استشهادًا |
| **المراجع** | بحث برقم المادة (1–1149) أو بكلمات، وقائمة بالمواد التي ظهرت في إجاباتك أثناء الجلسة؛ اضغط مادة لفتح نصها |
| **وضع نهاري / ليلي** | الزرّان أسفل القائمة الجانبية (أعلى الشاشة على الجوال) |
| الحالة | شارة «النظام جاهز» تتبع `/health` |

للتجربة بدون خادم: افتح `Frontend/index.html?mock=1`.

## 6) نقاط الـAPI

| الطريقة | المسار | الوظيفة |
|---|---|---|
| POST | `/ask` | سؤال وإجابة مع المصادر وحكم المراجِع |
| POST | `/ask/stream` | الإجابة بالبث |
| GET | `/search?q=` | استرجاع بدون توليد |
| GET | `/article/{n}` | نص مادة |
| POST | `/feedback` | تقييم إجابة |
| GET | `/health` `/ready` `/stats` `/cache/stats` `/metrics` | الحالة والمراقبة |
| `/cases...` | `POST /cases` ثم `POST /cases/{id}/documents` ثم `/ask` مع `case_id` | ملفات القضية |

## 7) شاشات المراقبة والتقييم

| الشاشة | الرابط | ماذا تجد |
|---|---|---|
| Prometheus Targets | :9090/targets | الهدف `civil-code-rag` بحالة UP |
| Prometheus Alerts | :9090/alerts | تنبيهات faithfulness وdrift وفشل المراجِع وزمن p95 |
| Grafana | :3000 (admin/admin ثم غيّر الكلمة) | أضف Prometheus كـData source بالعنوان `http://localhost:9090`، ثم Import لـ`monitoring/grafana/dashboards/civil_code_rag.json`: لوحة 20 رسمًا في 5 أقسام |
| MLflow | `mlflow ui --backend-store-uri sqlite:///mlflow.db` ثم :5000 | تجارب التقطيع (5 استراتيجيات) ونتائج RAGAS |
| Locust | `locust -f scripts/loadtest/locustfile.py --host http://localhost:8001` ثم :8089 | اختبار الحمل (على الخادم الوهمي) |

لوحتا RAGAS والـdrift في Grafana تبقيان فارغتين حتى تدفع نتائجهما عبر Pushgateway (`PROMETHEUS_PUSHGATEWAY_URL=http://localhost:9091`).

## 8) التقييم وسكربتات الصيانة

```powershell
pytest -q ; ruff check src tests scripts ; mypy src
python scripts/evaluation/eval_retrieval_offline.py --min-hit5 0.80
python scripts/evaluation/mlflow_chunking_experiments.py
python scripts/evaluation/run_evaluation.py --dataset data/eval/golden_set.json --ragas   # يحتاج الخدمة شغّالة
python scripts/evaluation/monitor_drift.py
python scripts/loadtest/loadtest_server_stub.py --port 8001       # ثم Locust
python scripts/data/make_review_checklist.py
```
تحذير: اختبار الحمل على الخدمة الحقيقية (8000) مع Voyage وTavily يعني استدعاءات مدفوعة؛ استخدم الخادم الوهمي (8001).

## 9) بعد الرفع إلى GitHub
1. مستودع Private، ثم `git push` إلى `main`.
2. قبل الدفع الأول: Settings → Secrets and variables → Actions → أضف `DOCKERHUB_USERNAME` و`DOCKERHUB_TOKEN` (توكن Read & Write من hub.docker.com).
3. تبويب Actions: `CI` (ruff وmypy وpytest وبوابة الاسترجاع وفحص المراقبة)، و`Docker` (يبني الصورة ويجرّبها ويدفعها إلى `<user>/civil-code-rag` على `main`).
4. الإعداد المحلي لا يتطلب مفاتيح لخدمات خارجية.

## 10) ما لم يُجرَّب
Docker، رسم لوحة Grafana فعليًا، RAGAS، وتشغيل الـworkflows على GitHub. راجع أول `/ready` عندك، وأرسل نص أي خطأ.


## سكربتات التشغيل على Windows (بدون Docker)

| الأمر | الوظيفة |
|---|---|
| `scripts\windows\setup.bat` | مرة واحدة: venv + تثبيت + `.env` + `OLLAMA_MODELS` + مسار الـembedding المحلي + بناء الفهرس + preflight |
| `scripts\windows\start.bat` | يشغّل Ollama ← API+الواجهة ويفتح المتصفح |
| `scripts\windows\start.bat -Monitoring -PrometheusDir "D:\AI-Models\Tools\prometheus-..." -GrafanaDir "D:\AI-Models\Tools\grafana-..."` | نفس السابق + Prometheus وGrafana |
| `scripts\windows\stop.bat [-Ollama]` | إيقاف أدوات المراقبة (واختيارياً Ollama) |

ضع مفاتيحك (`VOYAGE_API_KEY`, `TAVILY_API_KEY`) في `.env` بنفسك بعد `setup`.

### تنزيل أدوات المراقبة والاختبار (اختياري، تريدها كلها)

| الأمر | الوظيفة |
|---|---|
| `scripts\windows\install-monitoring.bat` | مرة واحدة: ينزّل Prometheus وGrafana (zip) إلى `D:\AI-Models\Tools` ويحفظ `PROMETHEUS_HOME` و`GRAFANA_HOME` (يحتاج إنترنت لهذه الخطوة فقط) |
| `scripts\windows\start.bat -Monitoring` | بعد فتح terminal جديد: يشغّل كل شيء، وGrafana يرتبط تلقائياً بـPrometheus ويحمّل اللوحة |
| `scripts\windows\loadtest.bat` | Locust على http://localhost:8089 ضد خادم stub (بلا تكلفة)؛ `-Real` ضد API الحقيقي (يستهلك Voyage/Tavily) |
| `scripts\windows\mlflow.bat [-Run]` | واجهة MLflow على http://localhost:5000؛ `-Run` يعيد تجارب التقطيع أولاً |
