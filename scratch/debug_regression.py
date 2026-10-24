import sys, os
# Add project src to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from src.api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

cases = [
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
]

for i, (question, expected) in enumerate(cases, 1):
    resp = client.post('/ask', json={"question": question, "debug": True})
    print(f"Case {i} status", resp.status_code)
    if resp.status_code != 200:
        print('Response text', resp.text)
        continue
    data = resp.json()
    debug = data.get('debug_info', [])
    article_numbers = [item.get('article_number') for item in debug if item.get('article_number')]
    missing = [a for a in expected if a not in article_numbers]
    print('Missing', missing)
