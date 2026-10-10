"""Thin helper around the LINE Messaging API reply calls."""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessageAction,
    MessagingApi,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)

from app.config import settings

configuration = Configuration(access_token=settings.line_channel_access_token)

# (label shown on the button, text sent when pressed)
QuickItems = Sequence[Tuple[str, str]]


def _build_quick_reply(items: Optional[QuickItems]) -> Optional[QuickReply]:
    if not items:
        return None
    return QuickReply(
        items=[
            QuickReplyItem(action=MessageAction(label=label, text=text))
            for label, text in items
        ]
    )


def reply_text(
    reply_token: str,
    text: str,
    quick_items: Optional[QuickItems] = None,
) -> None:
    message = TextMessage(text=text, quick_reply=_build_quick_reply(quick_items))
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[message])
        )
