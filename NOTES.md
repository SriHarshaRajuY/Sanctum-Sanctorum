# My Notes - Sanctum Sanctorum

## Live URL
Not deployed yet! I've just been testing locally with:
`uv run uvicorn app.main:app --reload`
I'm planning to push this up to Render and use a free Supabase Postgres db, but wanted to get all the tests passing first.

## Implementation details

I decided to keep the routers as dumb as possible. They basically just take the request, grab the DB session and the `get_now` dependency, and pass everything off to the services layer. I like this pattern because it makes testing the business logic way easier.

One tricky part was the stock reservation in orders. I wanted to make sure we don't accidentally decrement stock if an order fails validation halfway through. So, in `services/orders.py`, I load all the books upfront, check their stock and restrictions, and only if everything passes do we actually subtract the stock and commit. Same goes for the loans.

Also, dealing with money in cents is a lifesaver. I just used floor division (`//`) for the discount percentages so we don't have to deal with floating point weirdness.

## Stuff I'd improve later
- **Concurrency**: Right now, if two people try to buy the last copy of a book at the exact same millisecond, SQLite might let it happen or lock the db. If this was a real production app on Postgres, I'd definitely use `with_for_update()` to lock the book rows during the transaction.
- **Pagination on members**: Didn't get around to the optional `GET /members` endpoint with pagination yet.

## AI Usage
I used Claude to help me out with some of the boilerplate (like setting up the Pydantic schemas) and to rubber-duck a few SQLAlchemy 2.0 query syntax things. I used to write older SQLAlchemy (1.4 style) so I kept getting confused with the new `select(...)` syntax vs the old `query(...)` stuff. 
Claude was super helpful, but I did have to fix a bug it introduced where it was checking tier limits incorrectly (it did `tier > master` instead of allowing `master` as well).
