"""
Integration tests for the owner-only usage-stats CSV.

Covers the owner gate (any collection mode), and that the CSV carries the
expected snapshot counts and the aggregate age/postal breakdown.
"""

import csv as csvlib

from core.models import Collection, Thing, User

URL = "/api/v1/collections/{code}/stats/"


def _csv_dict(res):
    reader = csvlib.reader(res.content.decode().splitlines())
    return {row[0]: row[1] for row in reader if len(row) >= 2}


class TestCollectionStats:
    def _community(self, owner, code="COMM01"):
        return Collection.objects.create(
            code=code, owner=owner, headline="C", mode=Collection.Mode.COMMUNITY
        )

    def test_non_owner_forbidden(self, authenticated_client2, user):
        coll = self._community(user)
        res = authenticated_client2.get(URL.format(code=coll.code))
        assert res.status_code == 403

    def test_proprietary_collection_allowed(self, authenticated_client, user, user2):
        # Stats are available to the owner of ANY collection, not just COMMUNITY.
        coll = Collection.objects.create(
            code="PROP01", owner=user, headline="P", mode=Collection.Mode.PROPRIETARY
        )
        user2.age_range = "GEN_Z"
        user2.postal_code = "48001"
        user2.save()
        coll.invites.add(user2)

        res = authenticated_client.get(URL.format(code=coll.code))
        assert res.status_code == 200
        assert f"{coll.code}-stats.csv" in res["Content-Disposition"]
        data = _csv_dict(res)
        assert data["Members"] == "1"
        # One member: naming their bracket or their code would be naming them.
        assert "Born 1997-2012 (Gen Z)" not in data
        assert "Postal 48001" not in data
        assert data["Birth year shared by fewer than 3"] == "1"
        assert data["Postal, other codes"] == "1"

    def test_csv_counts_and_demographics(self, authenticated_client, user, user2):
        coll = self._community(user)
        user2.age_range = "GEN_Z"
        user2.postal_code = "48001"
        user2.save()
        m2 = User.objects.create(code="MEM002", email="m2@example.com")  # no demographics
        coll.invites.add(user2, m2)

        t1 = Thing.objects.create(
            code="TT0001", type="GIFT_THING", owner=user, headline="a", status="ACTIVE"
        )
        t2 = Thing.objects.create(
            code="TT0002", type="GIFT_THING", owner=user, headline="b", status="TAKEN"
        )
        coll.things.add(t1, t2)

        res = authenticated_client.get(URL.format(code=coll.code))
        assert res.status_code == 200
        assert res["Content-Type"].startswith("text/csv")
        assert "attachment" in res["Content-Disposition"]
        assert f"{coll.code}-stats.csv" in res["Content-Disposition"]

        data = _csv_dict(res)
        assert data["Members"] == "2"
        assert data["Things total"] == "2"
        assert data["Things active"] == "1"
        assert data["Things reserved"] == "1"
        assert "Born 1997-2012 (Gen Z)" not in data
        assert data["Birth year shared by fewer than 3"] == "1"
        assert data["Birth year not specified"] == "1"
        assert "Postal 48001" not in data
        assert data["Postal, other codes"] == "1"
        assert data["Postal not specified"] == "1"

    def test_a_bracket_or_a_code_is_named_from_three_members_up(self, authenticated_client, user):
        """Below three the figure is about a person; from three it is about a group.
        A bracket nobody is in is left out too, or the missing rows would name the
        small ones."""
        coll = self._community(user)
        for i, (age, postal) in enumerate(
            [("GEN_Z", "48001"), ("GEN_Z", "48001"), ("GEN_Z", "48001"), ("GEN_X", "08001")]
        ):
            coll.invites.add(
                User.objects.create(
                    code=f"MIN00{i}", email=f"m{i}@example.com", age_range=age, postal_code=postal
                )
            )

        data = _csv_dict(authenticated_client.get(URL.format(code=coll.code)))

        assert data["Born 1997-2012 (Gen Z)"] == "3"
        assert data["Postal 48001"] == "3"
        assert data["Birth year shared by fewer than 3"] == "1"
        assert data["Postal, other codes"] == "1"
        assert not any(label in data for label in ("Born 1965-1980 (Gen X)", "Postal 08001"))
        assert "Born 1981-1996 (Millennials)" not in data
