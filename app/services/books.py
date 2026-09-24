from typing import Optional
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Book
from app.schemas import BookCreate, BookPage, BookSort, BookUpdate


def create_book(db: Session, data: BookCreate) -> Book:
    # check if isbn already exists since it needs to be unique
    stmt = select(Book).where(Book.isbn == data.isbn)
    if db.scalar(stmt):
        raise HTTPException(status_code=409, detail="ISBN already exists in our system")
        
    new_book = Book(**data.model_dump())
    db.add(new_book)
    db.commit()
    db.refresh(new_book)
    
    return new_book


def get_book(db: Session, book_id: int) -> Book:
    b = db.get(Book, book_id)
    if not b:
        raise HTTPException(status_code=404, detail="Book not found")
    return b


def update_book(db: Session, book_id: int, data: BookUpdate) -> Book:
    b = get_book(db, book_id)
    
    # only update fields that were actually passed in
    update_data = data.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(b, key, val)
        
    db.commit()
    db.refresh(b)
    return b


def list_books(
    db: Session,
    q: Optional[str] = None,
    restricted: Optional[bool] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    sort: Optional[BookSort] = None,
    limit: int = 20,
    offset: int = 0,
) -> BookPage:
    
    stmt = select(Book)
    
    # apply filters
    if q:
        stmt = stmt.where(
            or_(Book.title.icontains(q), Book.author.icontains(q))
        )
    if restricted is not None:
        stmt = stmt.where(Book.restricted == restricted)
    if min_price is not None:
        stmt = stmt.where(Book.price_cents >= min_price)
    if max_price is not None:
        stmt = stmt.where(Book.price_cents <= max_price)

    # get total count before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_matches = db.scalar(count_stmt) or 0

    # handle sorting
    if sort == "title":
        stmt = stmt.order_by(Book.title.asc(), Book.id.asc())
    elif sort == "-title":
        stmt = stmt.order_by(Book.title.desc(), Book.id.asc())
    elif sort == "price":
        stmt = stmt.order_by(Book.price_cents.asc(), Book.id.asc())
    elif sort == "-price":
        stmt = stmt.order_by(Book.price_cents.desc(), Book.id.asc())
    else:
        # default sort
        stmt = stmt.order_by(Book.id.asc())

    # apply pagination
    stmt = stmt.limit(limit).offset(offset)
    results = db.scalars(stmt).all()

    return BookPage(items=results, total=total_matches, limit=limit, offset=offset)
