import uuid

from sqlmodel import Session

from app.db import ProcessedEvent, claim_event, engine, init_db


def test_claim_event_is_idempotent():
    init_db()
    event_id = f"test-{uuid.uuid4()}"

    # first time -> new, safe to process
    assert claim_event(event_id) is True
    # second time (redelivery) -> already handled
    assert claim_event(event_id) is False

    # missing id -> cannot dedupe, allow processing
    assert claim_event("") is True

    # cleanup
    with Session(engine) as session:
        row = session.get(ProcessedEvent, event_id)
        if row is not None:
            session.delete(row)
            session.commit()
