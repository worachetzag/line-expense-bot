"""Build human-friendly summary / confirmation messages."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Sequence, Tuple

from sqlmodel import Session, func, select

from app.db import Account, GroupMember, Transaction, group_members, now_local

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


def _short_id(user_id: str) -> str:
    return f"ผู้ใช้ {user_id[-4:]}" if user_id else "ไม่ทราบชื่อ"


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


def fetch_transactions_multi(
    session: Session, user_ids: Sequence[str], start: datetime, end: datetime
) -> List[Transaction]:
    if not user_ids:
        return []
    stmt = (
        select(Transaction)
        .where(
            Transaction.user_id.in_(list(user_ids)),
            Transaction.created_at >= start,
            Transaction.created_at < end,
        )
        .order_by(Transaction.created_at)
    )
    return list(session.exec(stmt).all())


# ---- balances --------------------------------------------------------------

@dataclass
class Balance:
    opening: float = 0.0
    income: float = 0.0
    expense: float = 0.0

    @property
    def balance(self) -> float:
        return self.opening + self.income - self.expense

    def __add__(self, other: "Balance") -> "Balance":
        return Balance(
            self.opening + other.opening,
            self.income + other.income,
            self.expense + other.expense,
        )


def _totals(session: Session, *conditions) -> Tuple[float, float]:
    stmt = (
        select(Transaction.type, func.sum(Transaction.amount))
        .where(*conditions)
        .group_by(Transaction.type)
    )
    income = 0.0
    expense = 0.0
    for tx_type, total in session.exec(stmt).all():
        value = float(total or 0)
        if tx_type == "income":
            income += value
        else:
            expense += value
    return income, expense


def personal_balance(session: Session, user_id: str) -> Balance:
    account = session.get(Account, user_id)
    opening = account.opening_balance if account else 0.0
    income, expense = _totals(session, Transaction.user_id == user_id)
    return Balance(opening, income, expense)


def group_balance(session: Session, group_id: str) -> Balance:
    total = Balance()
    for member in group_members(session, group_id):
        total = total + personal_balance(session, member.user_id)
    return total


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


def render_multi_confirmation(txs: Sequence[Transaction]) -> str:
    lines = [f"✅ บันทึกแล้ว {len(txs)} รายการ", "─────────────"]
    income = 0.0
    expense = 0.0
    for tx in txs:
        icon = "💚" if tx.type == "income" else "❤️"
        sign = "+" if tx.type == "income" else "-"
        line = f"{icon} {sign}{format_money(tx.amount)}  {tx.category}"
        if tx.note:
            line += f"  ({tx.note})"
        lines.append(line)
        if tx.type == "income":
            income += tx.amount
        else:
            expense += tx.amount
    lines.append("─────────────")
    lines.append(f"รวม รับ +{format_money(income)} / จ่าย -{format_money(expense)}")
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
    lines.append(f"📈 สุทธิ    {format_money(income - expense)}")
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


def render_balance_footer(bal: Balance) -> str:
    return (
        "─────────────\n"
        f"💰 คงเหลือ   {format_money(bal.balance)}\n"
        f"   ตั้งต้น {format_money(bal.opening)} · "
        f"รับ {format_money(bal.income)} · จ่าย {format_money(bal.expense)}"
    )


# ---- high level summaries --------------------------------------------------

def personal_summary(
    session: Session, user_id: str, title: str, start: datetime, end: datetime
) -> str:
    txs = fetch_transactions(session, user_id, start, end)
    body = render_summary(txs, title)
    return body + "\n" + render_balance_footer(personal_balance(session, user_id))


def group_summary(
    session: Session, group_id: str, title: str, start: datetime, end: datetime
) -> str:
    members: List[GroupMember] = group_members(session, group_id)
    if not members:
        return "ยังไม่มีข้อมูลในกลุ่มนี้ ลองพิมพ์บันทึกรายการก่อนนะ"

    user_ids = [m.user_id for m in members]
    txs = fetch_transactions_multi(session, user_ids, start, end)
    body = render_summary(txs, title)

    lines = ["", "👤 แยกตามคน"]
    for member in members:
        inc, exp = _totals(
            session,
            Transaction.user_id == member.user_id,
            Transaction.created_at >= start,
            Transaction.created_at < end,
        )
        bal = personal_balance(session, member.user_id)
        name = member.display_name or _short_id(member.user_id)
        lines.append(
            f"{name}: รับ +{format_money(inc)} จ่าย -{format_money(exp)} "
            f"| คงเหลือ {format_money(bal.balance)}"
        )

    total = group_balance(session, group_id)
    return body + "\n" + "\n".join(lines) + "\n" + render_balance_footer(total)


def summary_today(session: Session, user_id: str) -> str:
    start, end = period_today()
    return personal_summary(session, user_id, f"สรุปวันนี้ {thai_date(start)}", start, end)


def summary_week(session: Session, user_id: str) -> str:
    start, end = period_week()
    title = f"สรุปสัปดาห์ {thai_date(start)} - {thai_date(end - timedelta(days=1))}"
    return personal_summary(session, user_id, title, start, end)


def summary_month(session: Session, user_id: str) -> str:
    start, end = period_month()
    return personal_summary(session, user_id, f"สรุปเดือน {thai_month(start)}", start, end)


def group_summary_today(session: Session, group_id: str) -> str:
    start, end = period_today()
    return group_summary(session, group_id, f"สรุปคู่ {thai_date(start)}", start, end)


def help_text() -> str:
    return (
        "🤖 วิธีใช้\n"
        "─────────────\n"
        "บันทึกรายจ่าย:  50 กาแฟ\n"
        "บันทึกรายรับ:  +25000 เงินเดือน\n"
        "─────────────\n"
        "สรุป (วันนี้) / สรุปสัปดาห์ / สรุปเดือน\n"
        "สรุปคู่  (ในกลุ่ม: รวมทั้งคู่)\n"
        "ตั้งต้น 10000  (ตั้งเงินตั้งต้น/ยอดยกมา)\n"
        "ชื่อ <ชื่อ>  (ตั้งชื่อที่แสดงในสรุปคู่)\n"
        "หมวด / ลบล่าสุด / แก้ อาหาร"
    )
