# Regression tests for multiple legal scenarios (6 cases)

"""Each test sends a question to the /ask endpoint with debug=True and verifies
that the expected article numbers appear in the returned `debug_info`.
The expected answers are taken from the problem statements you provided.
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
            "عادل مرض الموت، وباع عقارًا لابنه وائل بسعر أقل من قيمته عند الوفاة، والفرق لا يتجاوز ثلث التركة. وهب أرضًا لابنته سلمى بعقد عرفي. واتفق مع ابنه باسل على أن يبيع الأخير نصيبه المتوقع من التركة لوائل، وعادل ما زال حيًا وموافق. هل يسري البيع في حق باقي الورثة؟ ما مصير الهبة؟ ما حكم اتفاق التنازل عن نصيب من التركة؟",
            [477, 488, 131],
        ),
        (
            "وكّل نادر أخاه مجدي شفاهة في بيع شقته، فباعها مجدي لليلى بعقد عرفي وقبض الثمن، وأنكر نادر الوكالة. دفعت ليلى مبلغ 20,000 جنيه زيادة على الثمن ظنًا منها أنها ملزمة بها ثم تبين العكس. أثناء غياب نادر سدّ جاره حاتم تسربًا عاجلًا في الشقة دون تكليف. هل تكفي الوكالة الشفوية؟ هل تسترد ليلى المبلغ الزائد؟ ما وصف تصرف حاتم؟",
            [700, 181, 179, 188],
        ),
        (
            "اتفق كمال وياسر شفاهة على شركة تجارية. اقترض كمال 100,000 جنيه من سعد، وكفله ماهر شفاهة. ثم أحال سعد دينه إلى وفاء دون علم كمال. كان لكمال على سعد دين نقدي غير متنازع فيه قدره 30,000 جنيه. ما أثر عدم كتابة عقد الشركة؟ هل تثبت الكفالة؟ هل تنفذ الحوالة في حق كمال؟ هل يستطيع كمال إجراء المقاصة مع دينه على سعد؟",
            [507, 773, 303, 305, 362],
        ),
    ],
)
def test_multiple_cases(question: str, expected_articles: list[int]):
    response = client.post("/ask", json={"question": question, "debug": True})
    assert response.status_code == 200, f"API returned {response.status_code}: {response.text}"
    data = response.json()
    debug = data.get("debug_info", [])
    article_numbers = get_article_numbers(debug)
    missing = [a for a in expected_articles if a not in article_numbers]
    assert not missing, f"Missing expected articles {missing} in debug info: {article_numbers}"
