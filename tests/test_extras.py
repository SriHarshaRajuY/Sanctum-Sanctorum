"""Tests for optional extras and edge cases:
- Paginated GET /members endpoint
- Inventory restoration and validation edge cases
"""
import pytest


class TestListMembers:
    """Tests for the optional GET /members endpoint with pagination."""

    def test_list_members_default_pagination(self, client, make_member):
        m1 = make_member(name="Member One", email="one@sanctum.org")
        m2 = make_member(name="Member Two", email="two@sanctum.org")

        response = client.get("/members")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert data["total"] == 2
        ids = [item["id"] for item in data["items"]]
        assert ids == [m1["id"], m2["id"]]

    def test_list_members_custom_limit_and_offset(self, client, make_member):
        members = [
            make_member(name=f"Member {i}", email=f"user{i}@sanctum.org")
            for i in range(1, 6)
        ]

        response = client.get("/members?limit=2&offset=1")
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert data["limit"] == 2
        assert data["offset"] == 1
        assert len(data["items"]) == 2
        assert data["items"][0]["id"] == members[1]["id"]
        assert data["items"][1]["id"] == members[2]["id"]

    @pytest.mark.parametrize(
        "params",
        [
            {"limit": 0},
            {"limit": 101},
            {"offset": -1},
        ],
    )
    def test_list_members_invalid_params_return_422(self, client, params):
        response = client.get("/members", params=params)
        assert response.status_code == 422


class TestInventoryIntegrityEdgeCases:
    """Tests for inventory integrity edge cases."""

    def test_cancelled_order_restores_exact_stock_across_multiple_items(
        self, client, make_member, make_book
    ):
        member = make_member()
        book_a = make_book(stock=10, price_cents=500)
        book_b = make_book(stock=5, price_cents=800)

        # Place an order for 3 copies of A and 2 copies of B
        order_resp = client.post(
            "/orders",
            json={
                "member_id": member["id"],
                "items": [
                    {"book_id": book_a["id"], "quantity": 3},
                    {"book_id": book_b["id"], "quantity": 2},
                ],
            },
        )
        assert order_resp.status_code == 201
        order_id = order_resp.json()["id"]

        # Stock should be reserved immediately
        assert client.get(f"/books/{book_a['id']}").json()["stock"] == 7
        assert client.get(f"/books/{book_b['id']}").json()["stock"] == 3

        # Cancel order
        cancel_resp = client.post(f"/orders/{order_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"

        # Stock must be completely restored
        assert client.get(f"/books/{book_a['id']}").json()["stock"] == 10
        assert client.get(f"/books/{book_b['id']}").json()["stock"] == 5
