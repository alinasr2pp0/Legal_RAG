from core.guardrails import redact_pii


def test_masks_phone_email_national_id():
    r = redact_pii("رقمي 01012345678 وايميلي a.b@mail.com والرقم القومي 29901011234567")
    assert "01012345678" not in r.text and "a.b@mail.com" not in r.text
    assert "29901011234567" not in r.text
    assert {"phone", "email", "national_id"} <= set(r.found)


def test_article_numbers_are_never_masked():
    r = redact_pii("ما نص المادة 163 والمادة 1149؟")
    assert not r.redacted and r.text == "ما نص المادة 163 والمادة 1149؟"


def test_arabic_indic_digits_detected():
    assert redact_pii("موبايلي ٠١٠١٢٣٤٥٦٧٨").redacted
