# My Notes - Sanctum Sanctorum

## Live URL
*(Pending public deployment — live link will be added upon hosting)*

To run and verify the application locally:
```bash
uv sync
uv run pytest
uv run uvicorn app.main:app --reload
```
To test out the application with demo data, open http://localhost:8000. You can sign in using seeded member ID `1` or `2` (or create a new member in the Members tab).

## What is complete
- **Books Catalogue**: Full CRUD, ISBN-13 normalization and checksum verification, pagination, title/author search, price filtering, and sorting.
- **Member Management**: Registration, email validation & normalization, tier access rules, order history, and live activity statistics.
- **Order Flow**: Order creation with price snapshots, tier and bulk discount calculations, atomic stock reservation, payment, and cancellation with automatic stock restoration.
- **Library Loans**: 14-day checkout period, tier limit enforcement, overdue checks, return handling, and capped late fee calculations.
- **Reports**: Top-selling books aggregated over paid orders.
- **Bonus Extras**:
  - **Concurrency Locking**: Added database row-level locking (`with_for_update()`) on books during both order checkout and loan borrowing, ordering by book ID to avoid deadlocks.
  - **Member Pagination**: Added a paginated `GET /members` endpoint with `limit` and `offset` query parameters and total count metadata.
  - **Edge-Case & Extra Tests**: Added focused tests in `tests/test_extras.py` covering member pagination and multi-item order cancellation inventory integrity (while leaving all original test files untouched).
  - **Database Compatibility**: Made database connection arguments dynamic in `app/db.py` (`check_same_thread` only applied for SQLite), ensuring smooth migration to hosted PostgreSQL (Supabase/Neon) without code changes.

## Architectural decisions & trade-offs

1. **Thin Routers & Pure Services**: Routers only handle request parsing, dependency injection (`Session`, `get_now`), and error formatting. All business rules, invariants, and database operations reside strictly in the service layer.
2. **Atomic Stock Updates & Invariants**: Operations that alter stock (orders and loans) validate all conditions first (member existence, restricted access, overdue loans, stock availability). Only when the entire operation is valid do we modify stock and persist the change.
3. **Deterministic Time**: All time calculations rely on the injected `get_now` dependency rather than calling `datetime.now()` directly. This keeps overdue boundaries strict and ensures testing is 100% deterministic.
4. **Integer Cent Arithmetic**: All monetary values are handled as integer cents, eliminating floating-point rounding errors. Discounts and late fees use integer floor division and explicit ceiling calculations.
5. **Database Engine Choice & Trade-offs**: SQLite is used for local tests and development to keep setup zero-dependency and test execution fast. For deployment, PostgreSQL is preferred because serverless environments have ephemeral filesystems where SQLite databases are wiped on restart.

## Spec observations & questions

- **Mixed-case sorting**: The spec noted that database engines disagree on sorting mixed-case strings (SQLite defaults to ASCII uppercase-first order, whereas Postgres collation often behaves case-insensitively). Following the spec, id-ascending order is used as the deterministic tie-breaker.
- **Tier boundary equality**: I made sure that tier access checks allow equality (e.g. `master` tier can access master-level restricted books, not strictly `> master`).
- **Late fee day calculation**: The spec defines late fees as 25 cents per started day late (`ceil((now - due_at) / 1 day)`), with the loan not considered overdue at exactly `due_at`. This strict boundary was implemented using ceiling division over total seconds.

## AI usage

I used Claude/ChatGPT to bounce ideas on modern SQLAlchemy 2.0 query patterns (especially the modern `select()` syntax with joins and `subquery()` counts) and to scaffold initial Pydantic schema constraints.
However, I had to critically review and adjust its suggestions:
- It initially wrote a naive tier comparison using strict inequality (`>`), which would have blocked `master` members from accessing restricted books.
- It also originally suggested naive `db.get()` calls for order creation and book borrowing, which lacked concurrency protection for book stock under high loads. I replaced this with an ordered `with_for_update()` lock.
