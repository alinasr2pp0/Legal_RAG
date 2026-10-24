import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
# -*- coding: utf-8 -*-
"""Regression tests for multiple legal scenarios.
Each test sends a question to the /ask endpoint with debug=True and verifies that
all expected article numbers appear in the returned `debug_info`.
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

# Helper to extract article numbers from debug info
def get_article_numbers(debug_info):
    return [item.get("article_number") for item in debug_info if item.get("article_number")]

@pytest.mark.parametrize(
    "question,expected_articles",
    [
        (
            "سُرقت سيارة منى في مارس 2025، باعها السارق لهاني في أسبوع من معرض يتاجر في مثلها مقابل 300,000 جنيه بحسن النية. علمت منى بمكان السيارة في أكتوبر 2026. هل يمكن لمنى استرداد السيارة؟ هل تلتزم بشيء لهاني؟ ما موقف عقد البيع الذي أبرمه السارق؟ هل تطالب السارق بتعويض وما مدة تقادم دعواها؟",
            [977, 466, 163, 221, 172, 207],
        ),
        (
            "أجرت شركة عقارية شقة لأحمد بعقد موحد لا يقبل التفاوض، ينص على غرامة 50,000 جنيه عن أي تأخر في الأجرة. تأخر أحمد ستة أشهر منذ 2019، والشركة رفعت دعواها في 2026 مطالبة بالأجرة والغرامة وفوائد على الفوائد. ما وصف العقد وقيمة قبول أحمد شروطه؟ هل تستحق الشركة الغرامة كاملة؟ هل تسقط مطالبة الأجرة المتأخرة؟ هل يجوز طلب فوائد على الفوائد؟",
            [100, 224, 375, 232, 226],
        ),
        (
            "بنى المقاول سيد عمارة بمشاركة المهندس رامي للمالك فؤاد وسُلمت عام 2020. في 2026 انهار جزء من الشرفة فأصيب المارة هدى وتلفت سيارة كريم بسبب عيب في الأرض وإهمال الصيانة. من يضمن للمالك الانهيار؟ من يسأل أمام هدى وكريم؟ هل يمكن مطالبة المسؤولين بالتضامن؟ ماذا يشمل تعويض هدى؟",
            [651, 177, 169, 221, 222],
        ),
        (
            "عادل مرض الموت وباع عقارًا لابنه وائل بسعر أقل من قيمته عند الوفاة، وهب أرضًا لابنته سلمى بعقد عرفي، واتفق مع ابنه باسل على بيع نصيب التركة لوائل. هل يسري البيع في حق باقي الورثة؟ ما مصير الهبة؟ ما حكم اتفاق التنازل عن نصيب من التركة؟",
            [477, 488, 131],
        ),
    ],
)
def test_multiple_cases(question: str, expected_articles: list[int]):
    resp = client.post("/ask", json={"question": question, "debug": True})
    assert resp.status_code == 200, f"API returned {resp.status_code}: {resp.text}"
    data = resp.json()
    debug = data.get("debug_info", [])
    article_numbers = get_article_numbers(debug)
    missing = [a for a in expected_articles if a not in article_numbers]
    assert not missing, f"Missing expected articles {missing} in debug info: {article_numbers}"
