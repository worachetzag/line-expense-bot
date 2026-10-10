"""Build human-friendly summary / confirmation messages."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable, List, Sequence, Tuple

from sqlmodel import Session, select

from app.db import Transaction, now_local

_THAI_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]


def format_money(value: float) -> str:
    return f"{value:,.2f}"


def thai_date(dt: datetime) -> str:
    return f"{dt.day} {_THAI_MONTHS[dt.month]} {dt.year + 543}"


def thai_month(dt: datetime) -> str:
    return f"{_THAI_MONTHS[dt.month]} {dt.year + 543}"


def _bar(value: float, max_value: float, width: int = 8) -> str:
    if max_value <= 0:
        return ""
    filled = max(1, round(value / max_value * width))
    filled = min(filled, width)
    return "▓" * filled + "░" * (width - filled)


# ---- date ranges -----------------------------------------------------------

def period_today(now: datetime | None = None) -> Tuple[datetime, datetime]:
    now = now or now_local()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def period_week(now: datetime | None = None) -> Tuple[datetime, datetime]:
    now = now or now_local()
    start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, start + timedelta(days=7)


def period_month(now: datetime | None = None) -> Tuple[datetime, datetime]:
    now = now or now_local()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (start + timedelta(days=32)).replace(day=1)
    return start, next_month


def fetch_transactions(
    session: Session, user_id: str, start: datetime, end: datetime
) -> List[Transaction]:
    stmt = (
        select(Transaction)
        .where(
            Transaction.user_id == user_id,
            Transaction.created_at >= start,
            Transaction.created_at < end,
        )
        .order_by(Transaction.created_at)
    )
    return list(session.exec(stmt).all())


# ---- rendering -------------------------------------------------------------

def render_confirmation(tx: Transaction) -> str:
    icon = "💚 รายรับ" if tx.type == "income" else "❤️ รายจ่าย"
    sign = "+" if tx.type == "income" else "-"
    lines = [
        "✅ บันทึกแล้ว",
        "─────────────",
        f"{icon}  {sign}{format_money(tx.amount)}",
        f"🏷️ หมวด: {tx.category}",
    ]
    if tx.note:
        lines.append(f"📝 {tx.note}")
    lines.append(f"🕒 {thai_date(tx.created_at)}")
    lines.append("")
    lines.append("ถ้าหมวดไม่ถูก กดปุ่มหรือพิมพ์: แก้ <ชื่อหมวด>")
    return "\n".join(lines)


def _summarize(txs: Sequence[Transaction]) -> Tuple[float, float, dict, dict]:
    income = 0.0
    expense = 0.0
    by_expense: dict[str, float] = defaultdict(float)
    by_income: dict[str, float] = defaultdict(float)
    for tx in txs:
        if tx.type == "income":
            income += tx.amount
            by_income[tx.category] += tx.amount
        else:
            expense += tx.amount
            by_expense[tx.category] += tx.amount
    return income, expense, by_expense, by_income


def render_summary(txs: Iterable[Transaction], title: str) -> str:
    txs = list(txs)
    income, expense, by_expense, by_income = _summarize(txs)

    lines = [f"📊 {title}", "─────────────"]
    lines.append(f"💚 รายรับ   +{format_money(income)}")
    lines.append(f"❤️ รายจ่าย  -{format_money(expense)}")
    lines.append(f"💰 คงเหลือ  {format_money(income - expense)}")
    lines.append(f"📌 {len(txs)} รายการ")

    if by_expense:
        lines.append("")
        lines.append("🔻 รายจ่ายแยกหมวด")
        max_value = max(by_expense.values())
        for category, amount in sorted(
            by_expense.items(), key=lambda kv: kv[1], reverse=True
        ):
            pct = (amount / expense * 100) if expense else 0
            lines.append(
                f"{category:<8} {_bar(amount, max_value)} "
                f"{format_money(amount)} ({pct:.0f}%)"
            )

    if by_income and len(by_income) > 1:
        lines.append("")
        lines.append("🔺 รายรับแยกหมวด")
        for category, amount in sorted(
            by_income.items(), key=lambda kv: kv[1], reverse=True
        ):
            lines.append(f"{category:<8} {format_money(amount)}")

    if not txs:
        lines.append("")
        lines.append("(ยังไม่มีรายการช่วงนี้)")

    return "\n".join(lines)


def summary_today(session: Session, user_id: str) -> str:
    start, end = period_today()
    txs = fetch_transactions(session, user_id, start, end)
    return render_summary(txs, f"สรุปวันนี้ {thai_date(start)}")


def summary_week(session: Session, user_id: str) -> str:
    start, end = period_week()
    txs = fetch_transactions(session, user_id, start, end)
    return render_summary(txs, f"สรุปสัปดาห์ {thai_date(start)} - {thai_date(end - timedelta(days=1))}")


def summary_month(session: Session, user_id: str) -> str:
    start, end = period_month()
    txs = fetch_transactions(session, user_id, start, end)
    return render_summary(txs, f"สรุปเดือน {thai_month(start)}")


def help_text() -> str:
    return (
        "🤖 วิธีใช้\n"
        "─────────────\n"
        "บันทึกรายจ่าย:  50 กาแฟ\n"
        "บันทึกรายรับ:  +25000 เงินเดือน\n"
        "─────────────\n"
        "สรุป (วันนี้)\n"
        "สรุปสัปดาห์\n"
        "สรุปเดือน\n"
        "หมวด  (ดูหมวดทั้งหมด)\n"
        "ลบล่าสุด  (ลบรายการล่าสุด)\n"
        "แก้ อาหาร  (เปลี่ยนหมวดรายการล่าสุด)"
    )
