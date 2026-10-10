import uuid

from sqlalchemy import delete
from sqlmodel import Session

from app.db import (
    Account,
    GroupMember,
    Transaction,
    engine,
    get_or_create_account,
    init_db,
    record_group_member,
)
from app.summary import group_balance, personal_balance, render_balance_footer


def _cleanup(session, user_ids, group_ids):
    session.exec(delete(Transaction).where(Transaction.user_id.in_(user_ids)))
    session.exec(delete(Account).where(Account.user_id.in_(user_ids)))
    if group_ids:
        session.exec(delete(GroupMember).where(GroupMember.group_id.in_(group_ids)))
    session.commit()


def test_personal_balance_includes_opening():
    init_db()
    uid = f"U-{uuid.uuid4().hex[:8]}"
    with Session(engine) as session:
        account = get_or_create_account(session, uid)
        account.opening_balance = 10000
        session.add(account)
        session.add(Transaction(user_id=uid, type="income", amount=25000, category="เงินเดือน"))
        session.add(Transaction(user_id=uid, type="expense", amount=1500, category="อาหาร"))
        session.commit()

        bal = personal_balance(session, uid)
        assert bal.opening == 10000
        assert bal.income == 25000
        assert bal.expense == 1500
        assert bal.balance == 33500
        assert "33,500.00" in render_balance_footer(bal)

        _cleanup(session, [uid], [])


def test_group_balance_sums_members():
    init_db()
    gid = f"G-{uuid.uuid4().hex[:8]}"
    u1 = f"U-{uuid.uuid4().hex[:8]}"
    u2 = f"U-{uuid.uuid4().hex[:8]}"
    with Session(engine) as session:
        for uid, opening, income in ((u1, 10000, 25000), (u2, 5000, 0)):
            account = get_or_create_account(session, uid)
            account.opening_balance = opening
            session.add(account)
            session.add(Transaction(user_id=uid, type="income", amount=income, category="อื่นๆ"))
            record_group_member(session, gid, uid, uid)
        session.commit()

        total = group_balance(session, gid)
        assert total.opening == 15000
        assert total.income == 25000
        assert total.balance == 40000

        _cleanup(session, [u1, u2], [gid])
