# Sanctum Sanctorum — Members' Bookstore API

A complete backend API for a members-only clubhouse bookstore built with FastAPI, SQLAlchemy 2.0, and SQLite. Members can buy books and borrow them from the club library.

## What's Implemented

This API is fully compliant with the project specifications and passes all 208 tests (including 202 original acceptance tests and 6 bonus/edge-case tests).

### Core Features
- **Books Catalogue**: Full CRUD with ISBN-13 checksum validation, filtering, sorting, and pagination.
- **Member Management**: Registration with tier-based access control (Apprentice, Adept, Master, Supreme) and activity stats tracking.
- **Orders & Purchasing**: Pending order creation with atomic stock reservation, tier-based and bulk discount calculations, and payment/cancellation flows.
- **Library Loans**: Borrowing rules enforced by tier limits, 14-day checkout periods, and automated late fee calculations capped at the book's price.
- **Reporting**: Top-selling books reports aggregated from paid orders.

### Bonus / Advanced Features added
- **Concurrency Locking**: Order creation and loan checkout use `with_for_update()` to ensure row-level database locks are acquired (ordered by book ID to prevent deadlocks). This ensures we never accidentally oversell the last copy of a book during concurrent requests.
- **Member Pagination**: Added full pagination (`limit`/`offset`) and total-count metadata to the `GET /members` endpoint.
- **Extra Edge-Case Tests**: Added `tests/test_extras.py` testing pagination boundary validation and inventory restoration invariants upon order cancellation.

## Architecture Highlights
- **Thin Routers, Thick Services**: The FastAPI routers only handle request parsing and dependency injection. All business rules, validation, and database commits happen in the service layer.
- **Atomic Transactions**: Complex operations like order creation and loan processing validate all constraints *before* mutating any stock, ensuring the database is never left in an invalid state.
- **Deterministic Time**: The `app.clock` dependency is used universally across the codebase to allow accurate time-travel testing for overdue loans.

## Quick Start

You can run the project using [uv](https://docs.astral.sh/uv/) (recommended) or standard `pip`.

### Using `uv`
```bash
uv sync                                  # install dependencies
uv run pytest                            # run the full test suite
uv run uvicorn app.main:app --reload     # start the API server locally
```

### Using standard pip (Python 3.10+)
```bash
python3 -m venv .venv
source .venv/bin/activate  # (or .venv\Scripts\activate on Windows)
pip install fastapi "uvicorn[standard]" "sqlalchemy>=2" "pydantic>=2" pytest httpx
pytest
uvicorn app.main:app --reload
```
