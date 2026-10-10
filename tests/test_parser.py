from app.parser import detect_command, parse_transaction


def test_expense_amount_before_note():
    tx = parse_transaction("50 กาแฟ")
    assert tx is not None
    assert tx.type == "expense"
    assert tx.amount == 50
    assert tx.note == "กาแฟ"
    assert tx.category == "อาหาร"


def test_expense_amount_after_note():
    tx = parse_transaction("กาแฟ 50")
    assert tx is not None
    assert tx.amount == 50
    assert tx.note == "กาแฟ"
    assert tx.category == "อาหาร"


def test_income_with_plus_prefix():
    tx = parse_transaction("+25000 เงินเดือน")
    assert tx is not None
    assert tx.type == "income"
    assert tx.amount == 25000
    assert tx.category == "เงินเดือน"


def test_thousands_separator_and_baht_noise():
    tx = parse_transaction("1,250 ค่าไฟ บาท")
    assert tx is not None
    assert tx.amount == 1250
    assert tx.category == "บิล"
    assert "บาท" not in tx.note


def test_amount_only_defaults_to_misc():
    tx = parse_transaction("99")
    assert tx is not None
    assert tx.amount == 99
    assert tx.category == "อื่นๆ"


def test_no_amount_returns_none():
    assert parse_transaction("สวัสดี") is None


def test_zero_amount_returns_none():
    assert parse_transaction("0 กาแฟ") is None


def test_detect_summary_today():
    assert detect_command("สรุป") == ("summary_today", "")
    assert detect_command(" สรุปวันนี้ ") == ("summary_today", "")


def test_detect_summary_month():
    assert detect_command("สรุปเดือน") == ("summary_month", "")


def test_detect_edit_category_with_arg():
    assert detect_command("แก้ อาหาร") == ("edit_category", "อาหาร")


def test_detect_edit_category_without_arg():
    assert detect_command("แก้") == ("edit_category", "")


def test_detect_help():
    assert detect_command("ช่วย") == ("help", "")


def test_detect_unknown_is_none():
    assert detect_command("กาแฟ 50") is None
