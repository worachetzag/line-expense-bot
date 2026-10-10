"""Import historical transactions from a Google Sheets CSV export.

The sheet layout is:
  col B: วันที่ (D/M/YYYY)  col C: ประเภท (รายรับ/รายจ่าย)
  col D: หมวดหมู่            col E: จำนวนเงิน
  col F: คงเหลือ (ignored)   col G: รายละเอียด

Usage:
  python -m scripts.import_sheet --file sheet.csv --user-id Uxxxx [--name ชื่อ] [--dry-run] [--force]

Re-running is safe: already-imported rows (raw_message starting with "import:")
are detected and the script refuses unless --force is given.
"""
from __future__ import annotations

import argparse
from datetime import datetime

from sqlalchemy import func
from sqlmodel import Session, select

from app.db import Transaction, engine, get_or_create_account, init_db

IMPORT_PREFIX = "import:"


def parse_money(value: str) -> float:
    cleaned = (value or "").replace("฿", "").replace(",", "").strip()
    return float(cleaned) if cleaned else 0.0


def parse_date(value: str) -> datetime:
    day, month, year = value.strip().split("/")
    return datetime(int(year), int(month), int(day), 12, 0, 0)


def load_rows(path: str) -> list[list[str]]:
    import csv

    with open(path, encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    header_idx = next(
        i for i, row in enumerate(rows) if any("วันที่" in cell for cell in row)
    )
    data = []
    for row in rows[header_idx + 1 :]:
        if len(row) <= 6 or not row[1].strip() or not row[3].strip():
            continue
        data.append(row)
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    init_db()
    rows = load_rows(args.file)
    print(f"rows in file: {len(rows)}")

    with Session(engine) as session:
        already = session.exec(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.user_id == args.user_id,
                Transaction.raw_message.startswith(IMPORT_PREFIX),
            )
        ).one()
        if already and not args.force:
            print(f"Already imported {already} rows for this user. Use --force to import again.")
            return

        if args.name:
            account = get_or_create_account(session, args.user_id)
            account.display_name = args.name
            session.add(account)
            session.commit()

        income = expense = 0.0
        for row in rows:
            date_s, type_s, category, amount_s, _balance, note = row[1:7]
            tx_type = "income" if type_s.strip() == "รายรับ" else "expense"
            amount = parse_money(amount_s)
            if tx_type == "income":
                income += amount
            else:
                expense += amount
            if args.dry_run:
                continue
            session.add(
                Transaction(
                    user_id=args.user_id,
                    type=tx_type,
                    amount=amount,
                    category=category.strip(),
                    note=note.strip(),
                    raw_message=IMPORT_PREFIX + ",".join(row),
                    created_at=parse_date(date_s),
                )
            )
        if not args.dry_run:
            session.commit()

    action = "would import" if args.dry_run else "imported"
    print(f"{action}: {len(rows)} rows  (income {income:,.2f} / expense {expense:,.2f})")


if __name__ == "__main__":
    main()
