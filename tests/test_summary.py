from datetime import datetime

from app.db import Transaction
from app.summary import (
    format_money,
    period_month,
    period_today,
    render_confirmation,
    render_summary,
    thai_date,
)


def _tx(tx_type: str, amount: float, category: str, note: str = "") -> Transaction:
    return Transaction(
        user_id="u1",
        type=tx_type,
        amount=amount,
        category=category,
        note=note,
        created_at=datetime(2026, 10, 10, 12, 0, 0),
    )


def test_format_money():
    assert format_money(1250) == "1,250.00"


def test_render_summary_totals():
    txs = [
        _tx("income", 25000, "เงินเดือน"),
        _tx("expense", 1250, "อาหาร"),
        _tx("expense", 800, "เดินทาง"),
    ]
    text = render_summary(txs, "ทดสอบ")
    assert "25,000.00" in text
    assert "2,050.00" in text
    assert "22,950.00" in text
    assert "อาหาร" in text
    assert "เดินทาง" in text
    assert "3 รายการ" in text


def test_render_summary_empty():
    text = render_summary([], "ทดสอบ")
    assert "ยังไม่มีรายการ" in text


def test_render_confirmation_expense():
    text = render_confirmation(_tx("expense", 50, "อาหาร", "กาแฟ"))
    assert "บันทึกแล้ว" in text
    assert "50.00" in text
    assert "กาแฟ" in text


def test_period_month_starts_on_first_day():
    start, end = period_month(datetime(2026, 10, 10, 15, 0, 0))
    assert start == datetime(2026, 10, 1, 0, 0, 0)
    assert end == datetime(2026, 11, 1, 0, 0, 0)


def test_period_today_bounds():
    start, end = period_today(datetime(2026, 10, 10, 15, 0, 0))
    assert start == datetime(2026, 10, 10, 0, 0, 0)
    assert end == datetime(2026, 10, 11, 0, 0, 0)


def test_thai_date_uses_buddhist_year():
    assert thai_date(datetime(2026, 10, 10)) == "10 ต.ค. 2569"
