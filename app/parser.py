"""Rule-based parser: turn a LINE text message into a transaction or a command."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

from app.categories import FALLBACK_CATEGORY, guess_category

# First standalone number in the message, allowing thousands separators / decimals.
_AMOUNT_RE = re.compile(r"(?<![\d.])(\d[\d,]*(?:\.\d+)?)(?![\d.])")

_INCOME_PREFIXES = ("+", "รายรับ", "รับ", "เงินเข้า", "income")
_EXPENSE_PREFIXES = ("-", "รายจ่าย", "จ่าย", "expense")

# Words stripped out of the note to keep it clean.
_NOISE_WORDS = ("บาท", "baht", "฿", "รายรับ", "รายจ่าย")


@dataclass
class ParsedTransaction:
    type: str  # "income" | "expense"
    amount: float
    note: str
    category: str
    raw: str


def _clean_note(note: str) -> str:
    for word in _NOISE_WORDS:
        note = note.replace(word, "")
    return note.strip(" \t-+.:").strip()


def extract_amount(text: str) -> Optional[float]:
    """Return the first number found in the text (or None)."""
    match = _AMOUNT_RE.search(text or "")
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def count_amounts(text: str) -> int:
    """How many standalone numbers appear in the text (0, 1, 2, ...)."""
    return len(_AMOUNT_RE.findall(text or ""))


def parse_transaction(text: str) -> Optional[ParsedTransaction]:
    """Parse "50 กาแฟ", "กาแฟ 50", "+25000 เงินเดือน" into a transaction.

    Returns None if no amount can be found.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    match = _AMOUNT_RE.search(raw)
    if not match:
        return None

    amount = float(match.group(1).replace(",", ""))
    if amount <= 0:
        return None

    note = _clean_note(raw[: match.start()] + " " + raw[match.end() :])

    lowered = raw.lower()
    tx_type = "expense"
    if lowered.startswith("+") or any(
        lowered.startswith(prefix) for prefix in _INCOME_PREFIXES[1:]
    ):
        tx_type = "income"
    elif lowered.startswith("-") or any(
        lowered.startswith(prefix) for prefix in _EXPENSE_PREFIXES[1:]
    ):
        tx_type = "expense"

    category = guess_category(note or raw, tx_type)
    return ParsedTransaction(
        type=tx_type,
        amount=amount,
        note=note,
        category=category,
        raw=raw,
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def detect_command(text: str) -> Optional[Tuple[str, str]]:
    """Detect a bot command. Returns (command, argument) or None.

    Recognized commands: help, categories, summary_today, summary_week,
    summary_month, delete_last, edit_category.
    """
    t = _normalize(text)
    if not t:
        return None

    if t in {"ช่วย", "ช่วยด้วย", "help", "วิธีใช้", "คำสั่ง", "?", "เมนู"}:
        return ("help", "")

    if t in {"หมวด", "หมวดหมู่", "categories", "category"}:
        return ("categories", "")

    if t in {"สรุปคู่", "สรุปบ้าน", "สรุปรวม", "สรุปทั้งคู่", "สรุปด้วยกัน", "สรุปครอบครัว"}:
        return ("summary_group", "")

    if t in {"สรุป", "สรุปวันนี้", "วันนี้", "summary"}:
        return ("summary_today", "")

    if t in {"สรุปสัปดาห์", "สัปดาห์", "อาทิตย์นี้", "สัปดาห์นี้", "week"}:
        return ("summary_week", "")

    if t in {"สรุปเดือน", "เดือนนี้", "เดือน", "month"}:
        return ("summary_month", "")

    if t in {"ลบล่าสุด", "ลบ", "undo", "ยกเลิกล่าสุด"}:
        return ("delete_last", "")

    for prefix in ("ตั้งต้น", "เงินตั้งต้น", "ยอดยกมา"):
        if t.startswith(prefix):
            arg = text.strip()[len(prefix):].strip(" :")
            return ("set_opening", arg)

    for prefix in ("แก้หมวด", "แก้", "เปลี่ยนหมวด", "หมวด:"):
        if t.startswith(prefix):
            arg = text.strip()[len(prefix):].strip(" :")
            return ("edit_category", arg)

    for prefix in ("ชื่อ", "ตั้งชื่อ"):
        if t.startswith(prefix):
            arg = text.strip()[len(prefix):].strip(" :")
            if arg:
                return ("set_name", arg)

    return None
