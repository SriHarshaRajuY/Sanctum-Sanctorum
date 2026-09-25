from datetime import datetime, timedelta
from math import ceil
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, Loan, MemberTier
from app.schemas import LoanCreate, LoanOut, LoanStatus
from app.services.members import ensure_can_access_restricted, get_member

# tier limits for concurrent active loans (None = unlimited)
TIER_LOAN_LIMIT = {
    MemberTier.APPRENTICE.value: 1,
    MemberTier.ADEPT.value: 3,
    MemberTier.MASTER.value: 5,
    MemberTier.SUPREME.value: None,
}

LOAN_DURATION = timedelta(days=14)
LATE_FEE_RATE_CENTS = 25  # per started day late


def loan_status(loan: Loan, now: datetime) -> LoanStatus:
    # status is computed dynamically at query time
    if loan.returned_at is not None:
        return "returned"
    if now > loan.due_at:
        return "overdue"
    return "active"


def to_loan_out(loan: Loan, now: datetime) -> LoanOut:
    return LoanOut(
        id=loan.id,
        member_id=loan.member_id,
        book_id=loan.book_id,
        borrowed_at=loan.borrowed_at,
        due_at=loan.due_at,
        returned_at=loan.returned_at,
        late_fee_cents=loan.late_fee_cents,
        status=loan_status(loan, now),
    )


def calculate_late_fee(due_at: datetime, returned_at: datetime, price_cents: int) -> int:
    # on-time returns owe nothing
    if returned_at <= due_at:
        return 0
    # any partial day counts as a full day late (ceiling)
    seconds_late = (returned_at - due_at).total_seconds()
    days_late = ceil(seconds_late / 86400.0)
    # late fee can never exceed the book's current price
    return min(days_late * LATE_FEE_RATE_CENTS, price_cents)


def create_loan(db: Session, data: LoanCreate, now: datetime) -> LoanOut:
    # 1. verify member and book exist
    member = get_member(db, data.member_id)

    # lock the book row to prevent race conditions on the last copy
    stmt = select(Book).where(Book.id == data.book_id).with_for_update()
    book = db.scalar(stmt)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # 2. check tier restriction
    if book.restricted:
        ensure_can_access_restricted(member)

    # 3. cannot borrow if any loan is overdue
    active_loans = [loan for loan in member.loans if loan.returned_at is None]
    if any(now > loan.due_at for loan in active_loans):
        raise HTTPException(status_code=409, detail="Member has overdue loans")

    # 4. cannot borrow multiple copies of the exact same book simultaneously
    if any(loan.book_id == book.id for loan in active_loans):
        raise HTTPException(status_code=409, detail="Already borrowed this title")

    # 5. tier borrowing limit check
    limit = TIER_LOAN_LIMIT.get(member.tier)
    if limit is not None and len(active_loans) >= limit:
        raise HTTPException(status_code=409, detail="Tier loan limit reached")

    # 6. check stock availability
    if book.stock <= 0:
        raise HTTPException(status_code=409, detail="Book is out of stock")

    # reserve a copy and create loan record
    book.stock -= 1
    new_loan = Loan(
        member_id=member.id,
        book_id=book.id,
        borrowed_at=now,
        due_at=now + LOAN_DURATION,
        returned_at=None,
        late_fee_cents=0,
    )
    db.add(new_loan)
    db.commit()
    db.refresh(new_loan)

    return to_loan_out(new_loan, now)


def get_loan(db: Session, loan_id: int, now: datetime) -> LoanOut:
    loan = db.get(Loan, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return to_loan_out(loan, now)


def return_loan(db: Session, loan_id: int, now: datetime) -> LoanOut:
    loan = db.get(Loan, loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.returned_at is not None:
        raise HTTPException(status_code=409, detail="Loan has already been returned")

    loan.returned_at = now
    loan.late_fee_cents = calculate_late_fee(loan.due_at, now, loan.book.price_cents)
    # put the copy back in stock
    loan.book.stock += 1

    db.commit()
    db.refresh(loan)
    return to_loan_out(loan, now)


def list_member_loans(
    db: Session, member_id: int, now: datetime, status: Optional[LoanStatus] = None
) -> List[LoanOut]:
    get_member(db, member_id)  # raises 404 if member doesn't exist
    stmt = select(Loan).where(Loan.member_id == member_id).order_by(Loan.id.asc())
    loans = db.scalars(stmt).all()

    results = [to_loan_out(loan, now) for loan in loans]
    if status is not None:
        results = [l for l in results if l.status == status]
    return results
