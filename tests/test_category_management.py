def test_bulk_create_categories(client):
    c, _ = client

    res = c.post(
        "/api/categories/bulk",
        json={
            "categories": [
                {"name": "Moonlit Waltz", "dimension": "GENRE"},
                {"name": "Glass Piano", "dimension": "INSTRUMENT", "description": "Bright prepared piano tone"},
            ]
        },
    )

    assert res.status_code == 200
    body = res.json()
    assert [item["name"] for item in body["categories"]] == ["Moonlit Waltz", "Glass Piano"]
    assert body["categories"][1]["description"] == "Bright prepared piano tone"

    listed = c.get("/api/categories").json()["categories"]
    names = {item["name"] for item in listed}
    assert {"Moonlit Waltz", "Glass Piano"}.issubset(names)


def test_delete_category_archives_and_hides_from_default_list(client):
    c, _ = client
    created = c.post(
        "/api/categories",
        json={"name": "Temporary Mood", "dimension": "MOOD"},
    ).json()

    deleted = c.delete(f"/api/categories/{created['id']}")

    assert deleted.status_code == 200
    assert deleted.json()["status"] == "ARCHIVED"

    active_ids = {item["id"] for item in c.get("/api/categories").json()["categories"]}
    assert created["id"] not in active_ids

    archived = c.get("/api/categories?include_archived=true").json()["categories"]
    archived_item = next(item for item in archived if item["id"] == created["id"])
    assert archived_item["status"] == "ARCHIVED"
