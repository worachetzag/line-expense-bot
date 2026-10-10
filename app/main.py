"""FastAPI app exposing the LINE webhook endpoint and message handling logic."""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import FollowEvent, MessageEvent, TextMessageContent

from app.categories import INCOME_CATEGORIES, EXPENSE_CATEGORIES, categories_for
from app.config import settings
from app.db import Transaction, engine, init_db
from app.line_client import QuickItems, reply_text
from app.parser import detect_command, parse_transaction
from app.summary import (
    format_money,
    help_text,
    render_confirmation,
    summary_month,
    summary_today,
    summary_week,
)

logger = logging.getLogger("line-expense-bot")

WELCOME = "สวัสดี! ฉันช่วยจดรายรับ-รายจ่ายให้\n\n" + help_text()

DEFAULT_QUICK: QuickItems = [
    ("สรุปวันนี้", "สรุปวันนี้"),
    ("สรุปเดือน", "สรุปเดือน"),
    ("ช่วย", "ช่วย"),
]

AFTER_SAVE_QUICK: QuickItems = [
    ("ลบล่าสุด", "ลบล่าสุด"),
    ("เปลี่ยนหมวด", "แก้"),
    ("สรุปวันนี้", "สรุปวันนี้"),
]

app = FastAPI(title="line-expense-bot")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
@app.get("/healthz")
def health() -> dict:
    return {"status": "ok"}


# ---- message handling ------------------------------------------------------

def _category_quick(tx_type: str) -> QuickItems:
    return [(c, f"แก้ {c}") for c in categories_for(tx_type)]


def _last_transaction(session: Session, user_id: str) -> Optional[Transaction]:
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


def _categories_text() -> str:
    return (
        "🏷️ หมวดที่มี\n"
        "─────────────\n"
        "รายจ่าย: " + ", ".join(EXPENSE_CATEGORIES) + "\n"
        "รายรับ: " + ", ".join(INCOME_CATEGORIES) + "\n\n"
        "พิมพ์: แก้ <ชื่อหมวด>  เพื่อเปลี่ยนหมวดรายการล่าสุด"
    )


def process_message(user_id: str, text: str) -> Tuple[str, Optional[QuickItems]]:
    """Return (reply text, quick reply items) for an incoming text message."""
    command = detect_command(text)

    with Session(engine) as session:
        if command is not None:
            name, arg = command

            if name == "help":
                return help_text(), DEFAULT_QUICK
            if name == "categories":
                return _categories_text(), DEFAULT_QUICK
            if name == "summary_today":
                return summary_today(session, user_id), DEFAULT_QUICK
            if name == "summary_week":
                return summary_week(session, user_id), DEFAULT_QUICK
            if name == "summary_month":
                return summary_month(session, user_id), DEFAULT_QUICK

            if name == "delete_last":
                last = _last_transaction(session, user_id)
                if last is None:
                    return "ไม่มีรายการให้ลบ", DEFAULT_QUICK
                label = last.note or last.category
                session.delete(last)
                session.commit()
                return (
                    f"🗑️ ลบแล้ว: {label} {format_money(last.amount)}",
                    DEFAULT_QUICK,
                )

            if name == "edit_category":
                last = _last_transaction(session, user_id)
                if last is None:
                    return "ยังไม่มีรายการให้แก้หมวด", DEFAULT_QUICK
                if not arg:
                    return (
                        "เลือกหมวดให้รายการล่าสุด:",
                        _category_quick(last.type),
                    )
                last.category = arg.strip()
                session.add(last)
                session.commit()
                session.refresh(last)
                return render_confirmation(last), AFTER_SAVE_QUICK

        parsed = parse_transaction(text)
        if parsed is not None:
            tx = Transaction(
                user_id=user_id,
                type=parsed.type,
                amount=parsed.amount,
                category=parsed.category,
                note=parsed.note,
                raw_message=parsed.raw,
            )
            session.add(tx)
            session.commit()
            session.refresh(tx)
            return render_confirmation(tx), AFTER_SAVE_QUICK

    return (
        "🤔 อันนี้ยังไม่เข้าใจ\n\n" + help_text(),
        DEFAULT_QUICK,
    )


# ---- LINE webhook ----------------------------------------------------------

handler = WebhookHandler(settings.line_channel_secret)


@handler.add(FollowEvent)
def on_follow(event: FollowEvent) -> None:
    reply_text(event.reply_token, WELCOME, DEFAULT_QUICK)


@handler.add(MessageEvent, message=TextMessageContent)
def on_text_message(event: MessageEvent) -> None:
    user_id = event.source.user_id
    text = event.message.text
    try:
        reply, quick = process_message(user_id, text)
    except Exception:  # noqa: BLE001 - never leave the user without a reply
        logger.exception("Failed to process message")
        reply, quick = "⚠️ เกิดข้อผิดพลาด ลองใหม่อีกครั้ง", DEFAULT_QUICK
    reply_text(event.reply_token, reply, quick)


@app.post("/callback")
async def callback(request: Request) -> str:
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")
    try:
        await run_in_threadpool(handler.handle, body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return "OK"
