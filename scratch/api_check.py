import sys, os
# add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)
question = "سُرقت سيارة منى في مارس 2025، باعها السارق لهاني في أسبوع من معرض يتاجر في مثلها مقابل 300,000 جنيه بحسن النية. علمت منى بمكان السيارة في أكتوبر 2026. هل يمكن لمنى استرداد السيارة؟ هل تلتزم بشيء لهاني؟ ما موقف عقد البيع الذي أبرمه السارق؟ هل تطالب السارق بتعويض وما مدة تقادم دعواها?"
resp = client.post('/ask', json={"question": question, "debug": True})
print('Status', resp.status_code)
if resp.status_code == 200:
    data = resp.json()
    print('Debug info:', data.get('debug_info'))
else:
    print('Response text', resp.text)
