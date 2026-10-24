from fastapi.testclient import TestClient

from api import main as api

client = TestClient(api.app)


def test_index_served_and_self_contained():
    r = client.get("/")
    assert r.status_code == 200 and 'dir="rtl"' in r.text
    assert "http://" not in r.text.replace("http://localhost:8000", "")  # no external URLs
    assert "https://" not in r.text


def test_article_endpoint():
    r = client.get("/article/163")
    assert r.status_code == 200
    body = r.json()
    assert body["article_number"] == 163 and "تعويض" in body["text"] and not body["is_repealed"]
    assert client.get("/article/54").json()["is_repealed"] is True
    assert client.get("/article/99999").status_code == 404


def test_cors_header_for_dev_origin():
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_ask_openapi_examples_do_not_invent_a_case_id():
    schema = client.get("/openapi.json").json()
    for path in ("/ask", "/ask/stream"):
        examples = schema["paths"][path]["post"]["requestBody"]["content"][
            "application/json"
        ]["examples"]
        assert examples["general_question"]["value"] == {
            "question": "ما هو التعويض عن الضرر؟"
        }


def test_chat_and_case_upload_ui_has_a_direct_question_path():
    html = client.get("/").text

    assert "اسأل عن المستندات" in html
    assert "أنا هنا لمساعدتك" not in html
    assert "بعد الرفع اسأل من صفحة المحادثة" not in html
    assert "على جهازك" not in html
