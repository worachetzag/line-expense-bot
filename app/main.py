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

from app.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES, categories_for
from app.config import settings
from app.db import (
    Transaction,
    claim_event,
    engine,
    get_or_create_account,
    init_db,
    prune_processed_events,
    record_group_member,
)
from app.line_client import QuickItems, get_profile_name, reply_text
from app.parser import detect_command, extract_amount, parse_transaction
from app.summary import (
    format_money,
    group_summary_today,
    help_text,
    personal_balance,
    render_confirmation,
    summary_month,
    summary_today,
    summary_week,
)

logger = logging.getLogger("line-expense-bot")

WELCOME = "สวัสดี! ฉันช่วยจดรายรับ-รายจ่ายให้\n\n" + help_text()

app = FastAPI(title="line-expense-bot")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    prune_processed_events()


@app.get("/")
@app.get("/healthz")
def health() -> dict:
    return {"status": "ok"}


# ---- quick replies ---------------------------------------------------------

def _quick(group_id: str = "") -> QuickItems:
    items: list = [("สรุปวันนี้", "สรุปวันนี้"), ("สรุปเดือน", "สรุปเดือน")]
    if group_id:
        items.append(("สรุปคู่", "สรุปคู่"))
    items.append(("ช่วย", "ช่วย"))
    return items


def _after_save_quick(group_id: str = "") -> QuickItems:
    items: list = [("ลบล่าสุด", "ลบล่าสุด"), ("เปลี่ยนหมวด", "แก้")]
    if group_id:
        items.append(("สรุปคู่", "สรุปคู่"))
    items.append(("สรุปวันนี้", "สรุปวันนี้"))
    return items


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


def _handle_set_opening(
    session: Session, user_id: str, arg: str, group_id: str
) -> Tuple[str, QuickItems]:
    account = get_or_create_account(session, user_id)
    amount = extract_amount(arg)
    if amount is None:
        bal = personal_balance(session, user_id)
        return (
            f"💰 เงินตั้งต้นของคุณ: {format_money(account.opening_balance)}\n"
            f"คงเหลือตอนนี้: {format_money(bal.balance)}\n\n"
            "ตั้งใหม่: ตั้งต้น 10000",
            _quick(group_id),
        )
    account.opening_balance = amount
    session.add(account)
    session.commit()
    bal = personal_balance(session, user_id)
    return (
        f"✅ ตั้งเงินตั้งต้นเป็น {format_money(amount)} แล้ว\n"
        f"💰 คงเหลือตอนนี้: {format_money(bal.balance)}",
        _quick(group_id),
    )


def process_message(
    user_id: str, text: str, group_id: str = ""
) -> Tuple[str, Optional[QuickItems]]:
    """Return (reply text, quick reply items) for an incoming text message."""
    command = detect_command(text)

    with Session(engine) as session:
        # Track group membership (and try to learn the sender's display name).
        if group_id:
            account = get_or_create_account(session, user_id)
            if not account.display_name:
                name = get_profile_name(user_id)
                if name:
                    account.display_name = name
                    session.add(account)
                    session.commit()
            record_group_member(session, group_id, user_id, account.display_name)

        if command is not None:
            name, arg = command

            if name == "help":
                return help_text(), _quick(group_id)
            if name == "categories":
                return _categories_text(), _quick(group_id)
            if name == "summary_today":
                return summary_today(session, user_id), _quick(group_id)
            if name == "summary_week":
                return summary_week(session, user_id), _quick(group_id)
            if name == "summary_month":
                return summary_month(session, user_id), _quick(group_id)

            if name == "summary_group":
                if not group_id:
                    return (
                        "คำสั่งนี้ใช้ในกลุ่มเท่านั้น (พิมพ์ สรุป สำหรับบัญชีตัวเอง)",
                        _quick(group_id),
                    )
                return group_summary_today(session, group_id), _quick(group_id)

            if name == "set_opening":
                return _handle_set_opening(session, user_id, arg, group_id)

            if name == "set_name":
                account = get_or_create_account(session, user_id)
                account.display_name = arg
                session.add(account)
                session.commit()
                if group_id:
                    record_group_member(session, group_id, user_id, arg)
                return f"✅ ตั้งชื่อที่แสดงเป็น «{arg}» แล้ว", _quick(group_id)

            if name == "delete_last":
                last = _last_transaction(session, user_id)
                if last is None:
                    return "ไม่มีรายการให้ลบ", _quick(group_id)
                label = last.note or last.category
                session.delete(last)
                session.commit()
                return (
                    f"🗑️ ลบแล้ว: {label} {format_money(last.amount)}",
                    _quick(group_id),
                )

            if name == "edit_category":
                last = _last_transaction(session, user_id)
                if last is None:
                    return "ยังไม่มีรายการให้แก้หมวด", _quick(group_id)
                if not arg:
                    return (
                        "เลือกหมวดให้รายการล่าสุด:",
                        _category_quick(last.type),
                    )
                last.category = arg.strip()
                session.add(last)
                session.commit()
                session.refresh(last)
                return render_confirmation(last), _after_save_quick(group_id)

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
            return render_confirmation(tx), _after_save_quick(group_id)

    return (
        "🤔 อันนี้ยังไม่เข้าใจ\n\n" + help_text(),
        _quick(group_id),
    )


# ---- LINE webhook ----------------------------------------------------------

handler = WebhookHandler(settings.line_channel_secret)


@handler.add(FollowEvent)
def on_follow(event: FollowEvent) -> None:
    if not claim_event(getattr(event, "webhook_event_id", "") or ""):
        logger.info("Ignoring duplicate follow event")
        return
    reply_text(event.reply_token, WELCOME, _quick())


@handler.add(MessageEvent, message=TextMessageContent)
def on_text_message(event: MessageEvent) -> None:
    if not claim_event(getattr(event, "webhook_event_id", "") or ""):
        logger.info("Ignoring duplicate message event")
        return
    source = event.source
    user_id = source.user_id
    group_id = getattr(source, "group_id", None) or getattr(source, "room_id", None) or ""
    text = event.message.text
    try:
        reply, quick = process_message(user_id, text, group_id)
    except Exception:  # noqa: BLE001 - never leave the user without a reply
        logger.exception("Failed to process message")
        reply, quick = "⚠️ เกิดข้อผิดพลาด ลองใหม่อีกครั้ง", _quick(group_id)
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
