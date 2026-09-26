# Sanctum Sanctorum — Project Notes & Implementation Review

## Live URL
*(Pending public deployment — live link will be added upon hosting)*

### How to Run and Test Locally
```bash
uv sync
uv run pytest
uv run uvicorn app.main:app --reload
```
To explore the application:
- **Interactive UI**: Open `http://localhost:8000` in your browser.
- **Demo Accounts**: Sign in using seeded member ID `1` (Stephen Strange, Master) or member ID `2` (Wong, Supreme), or create a fresh apprentice member in the Members tab.
- **Swagger / OpenAPI**: Interactive documentation is available at `http://localhost:8000/docs`.

---

## What I Finished

I completed all core requirements outlined in `SPEC.md`, ensuring 100% compliance with the 202 original acceptance tests:

1. **Books Catalogue**:
   - Implemented full CRUD with strict ISBN-13 normalization (stripping non-digit characters) and checksum validation.
   - White-space stripping for text fields (measuring length strictly post-strip).
   - Filtering by search query `q` (title or author substring), `restricted` status, and `min_price`/`max_price` ranges.
   - Dynamic sorting (`title`, `-title`, `price`, `-price`) with secondary `id` ascending tie-breaking, and pagination metadata (`total`, `limit`, `offset`).
   - Partial updates (`PATCH`) with silent ignoring of immutable/unknown fields.

2. **Member Management**:
   - Tier hierarchy enforcement (`apprentice` < `adept` < `master` < `supreme`).
   - Case-insensitive email normalization and regex verification.
   - Comprehensive member stats aggregation: paid order counts, total spent, active loans, overdue loans, and cumulative late fees.

3. **Orders & Inventory Management**:
   - Multi-item order placement with strict order of validation checks:
     1. Payload validation (422)
     2. Member & book existence (404)
     3. Tier access rules for restricted books (403)
     4. Stock sufficiency (409)
   - Atomic stock reservation at order creation; if any item is out of stock, no stock is altered and no order is persisted.
   - Precise integer discount calculations: tier discounts plus an additional 5% bulk discount for orders of 10 or more total items.
   - Order payment (`POST /orders/{id}/pay`) and cancellation (`POST /orders/{id}/cancel`) with automatic stock restoration.

4. **Library Loans**:
   - Tier-based concurrent borrowing limits (1 for Apprentice, 3 for Adept, 5 for Master, unlimited for Supreme).
   - Pre-condition enforcement: checks for overdue loans across the member's account, duplicate active borrows of the same title, tier limits, and available stock.
   - Deterministic 14-day loan duration.
   - Return processing: inventory replenishment and late fee calculation computed at 25 cents per started day (`ceil((now - due_at) / 1 day)`), capped at the book's current purchase price.

5. **Reporting**:
   - `GET /reports/top-books`: Aggregation of sales volume across paid orders, sorted by `copies_sold` descending with `title` ascending tie-breaking.

### Bonus / Optional Extras Added
- **Row-Level Concurrency Protection**: In both order creation and book borrowing, I implemented database row locking (`with_for_update()`). Critically, book IDs are locked in ascending order (`order_by(Book.id)`), which prevents deadlock scenarios when concurrent transactions attempt to reserve overlapping sets of books.
- **Paginated `GET /members` Endpoint**: Implemented full pagination with `limit` and `offset` query parameters, returning a structured `MemberPage` response with total member counts.
- **Edge-Case & Extra Tests**: Added [`tests/test_extras.py`](file:///f:/Placement%20Prep/Sanctum-Sanctorum-main/tests/test_extras.py) with 6 additional tests covering member pagination edge cases and multi-item stock restoration invariants, bringing total passing tests to **208**.
- **Database Engine Agnosticism**: Prepared `app/db.py` to seamlessly connect to PostgreSQL (e.g. Supabase, Neon) when `SANCTUM_DATABASE_URL` is set, dynamically omitting SQLite-specific arguments (`check_same_thread`).

---

## What I Would Do With More Time

If extending this into a production-grade service, here is what I would prioritize:
1. **Authentication & Authorization**: Replace client-supplied `member_id` with token-based authentication (JWT or OAuth2) so users can only view their own orders/loans, reserving administrative actions for staff roles.
2. **Alembic Database Migrations**: Introduce formal schema versioning with Alembic rather than relying on `Base.metadata.create_all()`.
3. **Asynchronous Background Tasks**: Add Celery or ARQ with Redis for scheduled reminders when loans are approaching `due_at` (e.g., 2 days prior to expiration).
4. **Automated Concurrency & Load Testing**: Write a dedicated locust or asyncio load test simulating high contention checkouts on a single remaining copy to benchmark row-lock contention under heavy traffic.

---

## Architectural Decisions & Trade-offs

1. **Strict Layering (Thin Routers, Pure Services)**:
   - *Decision*: Routers only handle request parsing, dependency injection (`Session`, `get_now`), and delegating to services. All domain rules, queries, and business validations reside exclusively in `app/services/`.
   - *Trade-off*: Adds a small amount of file boilerplate, but keeps routers trivially clean, ensures business logic is reusable, and simplifies unit/integration testing.

2. **All-or-Nothing Invariants (Pre-flight Validation)**:
   - *Decision*: During order creation and loan checkout, every prerequisite (existence, tier permissions, overdue status, inventory) is verified before making any mutations.
   - *Trade-off*: Reads must occur prior to writes, but this guarantees absolute database integrity: a failed order never leaves partial stock decrements or corrupted states.

3. **Deterministic Time Injection**:
   - *Decision*: I strictly avoided system `datetime.now()` calls. All domain logic depends on the injected `get_now` clock.
   - *Trade-off*: Requires passing `now` into service functions, but it makes time travel testing completely predictable and eliminated time-zone/jitter bugs around loan expiration boundaries.

4. **Integer Cent Monetary Arithmetic**:
   - *Decision*: Storing and calculating currency strictly as integer cents (`price_cents`, `discount_cents`, `total_cents`, `late_fee_cents`) using integer floor division (`//`) and math ceiling.
   - *Trade-off*: Requires dividing by 100 on the frontend for dollar display, but avoids floating-point inaccuracy (e.g. `$19.99 * 0.9` rounding issues).

5. **Database Strategy (SQLite locally vs. PostgreSQL in production)**:
   - *Decision*: Kept zero-dependency SQLite for local development and fast local test runs (`pytest`), while architecting `app/db.py` to accept PostgreSQL connection strings for deployed environments.
   - *Trade-off*: Serverless platforms have ephemeral filesystems where SQLite files reset between invocations; deploying to production requires a managed relational database like Supabase or Neon.

---

## Spec Observations & Edge Cases Noted

- **Strict Expiration Boundary (`due_at`)**: The spec establishes that at exactly `now == due_at`, a loan is still active and owes zero late fee. I made sure to use strict inequality (`now > due_at`) rather than greater-than-or-equal, correctly matching the requirement.
- **Late Fee Day Rounding**: Late fees specify 25 cents per *started* day. I used ceiling division over seconds (`math.ceil((now - due_at).total_seconds() / 86400)`) so that even 1 second into a new day accrues the full day's fee, capped at `book.price_cents`.
- **String Collation Differences**: As the spec points out, SQLite and Postgres sort mixed-case strings differently (ASCII uppercase-first vs. collation-aware). Relying on `order_by(Book.id.asc())` as the secondary sort key ensures that test assertions and pagination remain deterministic regardless of engine collation.

---

## AI Usage

I utilized AI (ChatGPT / Claude) as an accelerator for syntax reference and rapid exploration. Here is how I directed and audited its suggestions:

- **What I used it for**:
  - Quickly looking up SQLAlchemy 2.0 select statement idioms (such as modern `.subquery()` and `.scalar()` constructs).
  - Drafting initial regex patterns for ISBN-13 normalization and RFC-compliant email checking.
- **Where the AI was incorrect and I had to override it**:
  - *Tier Comparison Logic*: The AI initially wrote a strict inequality comparison (`member.tier > minimum_tier`). This would have caused `master` tier members to be denied access to master-restricted books. I caught this and implemented a proper `TIER_ORDER.index(tier) >= TIER_ORDER.index(minimum)` check.
  - *Concurrency & Stock Locking*: When asked to scaffold order creation, the AI suggested simple `db.get(Book, id)` calls followed by stock subtractions. This was prone to race conditions where two concurrent requests could both see stock `1` and oversell the book. I replaced this with an ordered `with_for_update()` query.
  - *Floating-Point Rounding*: The AI initially calculated late fees as `(days_late * 0.25) * 100`, which introduced floating-point representation quirks. I refactored all calculations to stay entirely within integer cents.
