from typing import List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Book, Order, OrderItem, OrderStatus
from app.schemas import TopBook


def top_books(db: Session, limit: int = 5) -> List[TopBook]:
    # aggregate copies sold across paid orders only
    # books with zero sales are excluded by the inner joins
    sales_count = func.sum(OrderItem.quantity).label("copies_sold")

    stmt = (
        select(Book.id, Book.title, sales_count)
        .join(OrderItem, OrderItem.book_id == Book.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status == OrderStatus.PAID.value)
        .group_by(Book.id, Book.title)
        .order_by(sales_count.desc(), Book.title.asc())
        .limit(limit)
    )

    rows = db.execute(stmt).all()
    return [
        TopBook(book_id=book_id, title=title, copies_sold=copies)
        for book_id, title, copies in rows
    ]
