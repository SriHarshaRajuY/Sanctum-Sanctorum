from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Book, MemberTier, Order, OrderItem, OrderStatus
from app.schemas import OrderCreate
from app.services.members import ensure_can_access_restricted, get_member

# mapping tiers to their base discount percentages
TIER_DISCOUNTS = {
    MemberTier.APPRENTICE.value: 0,
    MemberTier.ADEPT.value: 5,
    MemberTier.MASTER.value: 10,
    MemberTier.SUPREME.value: 15,
}

def get_discount_rate(member, total_qty: int) -> int:
    # get base discount
    rate = TIER_DISCOUNTS.get(member.tier, 0)
    # add bulk bonus if they buy 10 or more items
    if total_qty >= 10:
        rate += 5
    return rate

def create_order(db: Session, data: OrderCreate, now: datetime) -> Order:
    member = get_member(db, data.member_id)

    # load all books upfront with a row-level lock to prevent concurrent overselling
    # sorting by id prevents deadlocks if multiple transactions lock the same books
    book_ids = [item.book_id for item in data.items]
    stmt = select(Book).where(Book.id.in_(book_ids)).order_by(Book.id).with_for_update()
    locked_books = db.scalars(stmt).all()
    book_map = {b.id: b for b in locked_books}

    for item in data.items:
        if item.book_id not in book_map:
            raise HTTPException(status_code=404, detail=f"Book {item.book_id} not found")

    # check if they're allowed to buy restricted books
    has_restricted = any(b.restricted for b in book_map.values())
    if has_restricted:
        ensure_can_access_restricted(member)

    # check stock limits (all or nothing)
    for item in data.items:
        if book_map[item.book_id].stock < item.quantity:
            raise HTTPException(status_code=409, detail="Not enough stock for one or more items")

    # calculate totals
    total_qty = sum(item.quantity for item in data.items)
    subtotal = sum(book_map[item.book_id].price_cents * item.quantity for item in data.items)
    
    discount_pct = get_discount_rate(member, total_qty)
    discount_amount = subtotal * discount_pct // 100
    
    # create the actual order record
    new_order = Order(
        member_id=member.id,
        status=OrderStatus.PENDING.value,
        subtotal_cents=subtotal,
        discount_percent=discount_pct,
        discount_cents=discount_amount,
        total_cents=subtotal - discount_amount,
        created_at=now,
    )
    
    # deduct stock and create order items
    for item in data.items:
        b = book_map[item.book_id]
        b.stock -= item.quantity
        new_order.items.append(
            OrderItem(book_id=b.id, quantity=item.quantity, unit_price_cents=b.price_cents)
        )

    db.add(new_order)
    db.commit()
    db.refresh(new_order)
    
    return new_order

def get_order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

def pay_order(db: Session, order_id: int) -> Order:
    order = get_order(db, order_id)
    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Only pending orders can be paid")
    
    order.status = OrderStatus.PAID.value
    db.commit()
    db.refresh(order)
    return order

def cancel_order(db: Session, order_id: int) -> Order:
    order = get_order(db, order_id)
    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Only pending orders can be cancelled")
    
    # give the stock back!
    for item in order.items:
        item.book.stock += item.quantity
        
    order.status = OrderStatus.CANCELLED.value
    db.commit()
    db.refresh(order)
    return order
