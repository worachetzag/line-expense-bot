"""Optional LLM fallback: turn free-form Thai text into structured transactions.

Used only when the rule-based parser cannot find an amount, and only when
LLM_BASE_URL / LLM_API_KEY / LLM_MODEL are configured (OpenAI-compatible API).
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

import httpx

from app.categories import guess_category
from app.config import settings
from app.parser import ParsedTransaction

logger = logging.getLogger("line-expense-bot.llm")

_SYSTEM_PROMPT = (
    "คุณเป็นตัวแปลงข้อความภาษาไทยเป็นรายการรายรับ-รายจ่าย\n"
    "ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น รูปแบบ:\n"
    '{"transactions":[{"type":"expense","amount":60,"category":"อาหาร","note":"ข้าวมันไก่"}]}\n'
    "กติกา:\n"
    '- type คือ "income" (รายรับ) หรือ "expense" (รายจ่าย) ค่าเริ่มต้นคือ expense\n'
    "- amount เป็นตัวเลขบาท (ไม่ต้องมี ฿ หรือ ,)\n"
    "- ถ้าข้อความมีหลายรายการ ให้แยกเป็นหลาย object\n"
    "- category เลือกที่ใกล้ที่สุดจาก: อาหาร, เดินทาง, ช้อปปิ้ง, บิล, ที่พัก, สุขภาพ, "
    "บันเทิง, การศึกษา, เงินเดือน, โบนัส, ขายของ, ดอกเบี้ย, อื่นๆ\n"
    "- note คือรายละเอียดสั้น ๆ\n"
    '- ถ้าไม่ใช่รายการการเงิน ให้ตอบ {"transactions":[]}'
)


def is_enabled() -> bool:
    return bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model)


def _extract_json(content: str) -> dict:
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return {}


def parse_with_llm(text: str) -> Optional[List[ParsedTransaction]]:
    """Return a list of parsed transactions, or None if unavailable/nothing found."""
    if not is_enabled():
        return None

    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            },
            timeout=20.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001 - fallback must never crash the bot
        logger.exception("LLM parse failed")
        return None

    payload = _extract_json(content or "")
    result: List[ParsedTransaction] = []
    for item in payload.get("transactions", []) or []:
        try:
            amount = float(item.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        tx_type = "income" if item.get("type") == "income" else "expense"
        note = str(item.get("note") or "").strip()
        category = str(item.get("category") or "").strip() or guess_category(
            note, tx_type
        )
        result.append(
            ParsedTransaction(
                type=tx_type,
                amount=amount,
                note=note,
                category=category,
                raw=text,
            )
        )
    return result or None
