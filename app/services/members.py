from datetime import datetime
from typing import List

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Member, MemberTier, Order, OrderStatus
from app.schemas import MemberCreate, MemberStats, MemberPage

TIER_ORDER = [
    MemberTier.APPRENTICE.value,
    MemberTier.ADEPT.value,
    MemberTier.MASTER.value,
    MemberTier.SUPREME.value,
]

# you need to be at least a master to get restricted books
RESTRICTED_MIN_TIER = MemberTier.MASTER.value

def tier_at_least(tier: str, minimum: str) -> bool:
    return TIER_ORDER.index(tier) >= TIER_ORDER.index(minimum)

def ensure_can_access_restricted(member: Member) -> None:
    if not tier_at_least(member.tier, RESTRICTED_MIN_TIER):
        raise HTTPException(
            status_code=403, 
            detail=f"Restricted books require tier '{RESTRICTED_MIN_TIER}' or higher"
        )

def create_member(db: Session, data: MemberCreate, now: datetime) -> Member:
    # check if email is taken (it's already lowercased by pydantic)
    if db.scalar(select(Member).where(Member.email == data.email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
        
    new_member = Member(name=data.name, email=data.email, tier=data.tier.value, created_at=now)
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    
    return new_member

def get_member(db: Session, member_id: int) -> Member:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member

def list_members(db: Session, limit: int = 20, offset: int = 0) -> MemberPage:
    stmt = select(Member).order_by(Member.id.asc())
    
    # get the total count for pagination metadata
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = db.scalar(count_stmt) or 0
    
    members = db.scalars(stmt.limit(limit).offset(offset)).all()
    
    return MemberPage(items=members, total=total_count, limit=limit, offset=offset)

def list_member_orders(db: Session, member_id: int) -> List[Order]:
    get_member(db, member_id)  # just to raise 404 if missing
    stmt = select(Order).where(Order.member_id == member_id).order_by(Order.id)
    return list(db.scalars(stmt))

def get_member_stats(db: Session, member_id: int, now: datetime) -> MemberStats:
    m = get_member(db, member_id)
    
    paid_orders = [o for o in m.orders if o.status == OrderStatus.PAID.value]
    unreturned_loans = [L for L in m.loans if L.returned_at is None]
    overdue = [L for L in unreturned_loans if now > L.due_at]
    returned_loans = [L for L in m.loans if L.returned_at is not None]
    
    return MemberStats(
        member_id=m.id,
        orders_paid=len(paid_orders),
        total_spent_cents=sum(o.total_cents for o in paid_orders),
        active_loans=len(unreturned_loans),
        overdue_loans=len(overdue),
        late_fees_cents=sum(L.late_fee_cents for L in returned_loans),
    )
