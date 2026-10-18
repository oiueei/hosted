"""The multilingual demo seed (one seeding serves every reader).

Collection/thing headlines, descriptions and tag labels are seeded as localized
``{"es": …, "ca": …, "en": …}`` maps built from ALL the language files;
``--lang`` only picks the language of the plain-column text (user bios, FAQs).
These tests pin the merge, the parity between language files
(the seed analogue of ``i18nParity``), the per-language length limits the
serializers would otherwise enforce, and the raw-string tag consistency the
subset check depends on.
"""

from importlib import import_module

import pytest
from django.core.management import call_command
from django.test import override_settings

from core.management.commands.seed_data import common
from core.management.commands.seed_demo import (
    _MERGE_KEYS,
    DEMO_USER_CODES,
    SUPPORTED_LANGS,
    _localize,
    load_seed_data,
)
from core.models import Collection, Thing, User
from core.utils import parse_localized, resolve_localized

LANG_MODULES = {
    code: import_module(f"core.management.commands.seed_data.{code}") for code in SUPPORTED_LANGS
}

# Visible (per-language) and storage caps — mirror the Localized* serializer fields.
HEADLINE_LIMIT, HEADLINE_STORAGE = 64, 256
DESCRIPTION_LIMIT, DESCRIPTION_STORAGE = 2000, 6400
TAG_LIMIT, TAG_STORAGE = 32, 160


class TestLocalize:
    def test_identical_variants_stay_a_plain_string(self):
        assert _localize({"es": "Arduino", "ca": "Arduino", "en": "Arduino"}) == "Arduino"

    def test_distinct_variants_become_a_strict_map(self):
        value = _localize({"es": "Cocina", "ca": "Cuina", "en": "Kitchen"})
        assert parse_localized(value) == {"es": "Cocina", "ca": "Cuina", "en": "Kitchen"}

    def test_missing_variants_are_dropped_not_stored_empty(self):
        value = _localize({"es": "Hola", "ca": "", "en": "Hi"})
        assert parse_localized(value) == {"es": "Hola", "en": "Hi"}

    def test_all_empty_is_empty(self):
        assert _localize({"es": "", "ca": "", "en": ""}) == ""


class TestDemoCollectionsSayTheyAreDemos:
    """A demo collection is a demo before anyone opens it: its title says so in every
    language, and still fits the visible limit the serializer enforces. The things
    inside are not marked: the collection is what is the demo."""

    @pytest.mark.parametrize("code", SUPPORTED_LANGS)
    def test_every_collection_title_starts_with_demo_and_fits(self, code):
        module = LANG_MODULES[code]
        for collection in module.COLLECTIONS:
            title = collection["headline"]
            assert title.startswith("DEMO · "), f"{code} {collection['code']}: {title!r}"
            assert len(title) <= HEADLINE_LIMIT, f"{code} {collection['code']}: {len(title)}"

    @pytest.mark.parametrize("code", SUPPORTED_LANGS)
    def test_no_thing_title_does(self, code):
        assert not any(t["headline"].startswith("DEMO") for t in LANG_MODULES[code].THINGS)

    def test_the_seeded_row_carries_it_in_all_three_languages(self):
        call_command("seed_demo", lang="en", verbosity=0)

        for collection in Collection.objects.filter(is_onboarding=True):
            titles = parse_localized(collection.headline) or {}
            assert titles, collection.code
            assert all(text.startswith("DEMO · ") for text in titles.values()), collection.code


class TestSeedFileParity:
    """Every language file must translate the same rows and the same fields."""

    @pytest.mark.parametrize("entity", ["USERS", "COLLECTIONS", "THINGS", "FAQS"])
    def test_same_rows_and_fields_in_every_language(self, entity):
        key = _MERGE_KEYS[entity]
        reference = {row[key]: set(row) for row in getattr(LANG_MODULES["en"], entity)}
        for code in SUPPORTED_LANGS:
            rows = {row[key]: set(row) for row in getattr(LANG_MODULES[code], entity)}
            assert rows.keys() == reference.keys(), f"{code}.{entity} rows differ from en"
            for row_key, fields in rows.items():
                assert fields == reference[row_key], f"{code}.{entity}[{row_key}] fields differ"

    def test_per_language_texts_fit_the_visible_limits(self):
        for code, module in LANG_MODULES.items():
            for row in module.COLLECTIONS + module.THINGS:
                assert len(row.get("headline", "")) <= HEADLINE_LIMIT, (code, row)
                assert len(row.get("description", "")) <= DESCRIPTION_LIMIT, (code, row)
            for row in module.USERS:
                assert len(row.get("headline", "")) <= HEADLINE_LIMIT, (code, row)
            for row in module.FAQS:
                assert len(row["question"]) <= 64 and len(row["answer"]) <= 256, (code, row)


class TestMergedSeedData:
    def test_collection_text_resolves_per_reader_language(self):
        data = load_seed_data("en")
        headline = next(c for c in data.COLLECTIONS if c["code"] == "l1l1C1")["headline"]
        assert parse_localized(headline) is not None
        for code in SUPPORTED_LANGS:
            expected = next(
                c for c in getattr(LANG_MODULES[code], "COLLECTIONS") if c["code"] == "l1l1C1"
            )["headline"]
            assert resolve_localized(headline, code) == expected

    # The "language-neutral text stays plain" case used to be asserted here on a
    # seed row (the electronics jargon in the removed swap collection). No seeded
    # text reads the same in all three languages any more, so the rule is pinned
    # where it actually lives: TestLocalize above, on ``_localize`` itself.

    def test_merged_values_fit_the_storage_columns(self):
        data = load_seed_data("en")
        for row in data.COLLECTIONS:
            assert len(row["headline"]) <= HEADLINE_STORAGE, row["code"]
            assert len(row["description"]) <= DESCRIPTION_STORAGE, row["code"]
            for tag in row.get("tags", []):
                assert len(tag) <= TAG_STORAGE, (row["code"], tag)
        for row in data.THINGS:
            assert len(row["headline"]) <= HEADLINE_STORAGE, row["code"]
            assert len(row["description"]) <= DESCRIPTION_STORAGE, row["code"]

    def test_tag_labels_fit_the_per_language_limit(self):
        for row in common.COLLECTIONS:
            for tag in row.get("tags", []):
                texts = parse_localized(tag)
                for text in (texts or {tag: tag}).values():
                    assert len(text) <= TAG_LIMIT, tag

    def test_thing_tags_are_a_raw_string_subset_of_their_collection_vocabulary(self):
        # The subset check in production compares RAW strings — a thing tag must
        # be byte-identical to a vocabulary entry (the constants in common.py).
        vocab = {c["code"]: set(c.get("tags", [])) for c in common.COLLECTIONS}
        for thing in common.THINGS:
            for col_code in thing.get("collections", []):
                for tag in thing.get("tags", []):
                    assert tag in vocab[col_code], (thing["code"], tag)


@pytest.mark.django_db
class TestSeedCommand:
    def test_seeds_localized_maps_and_is_idempotent(self):
        call_command("seed_demo", lang="ca", verbosity=0)
        call_command("seed_demo", lang="ca", verbosity=0)  # idempotent re-run

        collection = Collection.objects.get(code="l1l1C1")
        assert resolve_localized(collection.headline, "ca").startswith("DEMO · Préstecs de la Lili")
        assert resolve_localized(collection.headline, "es").startswith("DEMO · Préstamos de Lili")
        assert resolve_localized(collection.headline, "en")  # English present too

        thing = Thing.objects.get(code="l1l101")
        assert parse_localized(thing.headline) is not None
        # The thing's tag is the same raw string as the vocabulary entry.
        assert set(thing.tags) <= set(collection.tags)

        # Non-localizable text followed --lang=ca.
        faq = thing.owner.asked_faqs.model.objects.filter(thing_id="La1a01").first()
        assert faq is not None and faq.question == "Puc recollir-ho a final de mes?"


@pytest.mark.django_db
class TestSeedEmailDomain:
    """The demo characters' address: `SEED_EMAIL_DOMAIN`, a reserved `.test` by default."""

    @staticmethod
    def _emails():
        return set(User.objects.filter(code__in=DEMO_USER_CODES).values_list("email", flat=True))

    def test_the_default_is_a_domain_that_cannot_exist(self):
        call_command("seed_demo", lang="en", verbosity=0)

        assert self._emails() == {
            f"{name}@your-domain.test" for name in ("lala", "lele", "lili", "lolo", "lulu")
        }

    @override_settings(SEED_EMAIL_DOMAIN="otra.test")
    def test_a_deployment_names_its_own_domain(self):
        call_command("seed_demo", lang="en", verbosity=0)

        assert self._emails() == {
            f"{name}@otra.test" for name in ("lala", "lele", "lili", "lolo", "lulu")
        }

    def test_running_it_again_with_another_domain_moves_the_five_in_place(self):
        call_command("seed_demo", lang="en", verbosity=0)
        before = User.objects.count()

        with override_settings(SEED_EMAIL_DOMAIN="otra.test"):
            call_command("seed_demo", lang="en", verbosity=0)

        assert User.objects.count() == before
        assert self._emails() == {
            f"{name}@otra.test" for name in ("lala", "lele", "lili", "lolo", "lulu")
        }


@pytest.mark.django_db
class TestRelaunchingTheSeedLeavesEveryoneElseWhereTheyAre:
    """The seed places its own five characters in a demo group, and nobody else."""

    GROUP = "1u1uC1"  # the characters are members; La1aN1 co-curates it

    @staticmethod
    def _people(group, relation):
        return set(getattr(group, relation).values_list("code", flat=True))

    def _join_real_people(self):
        group = Collection.objects.get(code=self.GROUP)
        member = User.objects.create(code="REAL01", email="lila@your-domain.test", name="Real")
        curator = User.objects.create(code="REAL02", email="lola@your-domain.test", name="Curator")
        group.invites.add(member, curator)
        group.co_owners.add(curator)
        thing = Thing.objects.create(code="RTHNG1", owner=member, headline="Una taladradora")
        group.things.add(thing)
        return group, member, curator, thing

    def test_a_real_member_a_real_curator_and_their_thing_survive_the_relaunch(self):
        call_command("seed_demo", lang="en", verbosity=0)
        group, member, curator, thing = self._join_real_people()

        call_command("seed_demo", lang="en", verbosity=0)

        group.refresh_from_db()
        assert {member.code, curator.code} <= self._people(group, "invites")
        assert curator.code in self._people(group, "co_owners")
        assert group.things.filter(code=thing.code).exists()
        assert Thing.objects.filter(code=thing.code).exists()

    def test_a_character_the_seed_no_longer_places_there_leaves(self):
        call_command("seed_demo", lang="en", verbosity=0)
        group = Collection.objects.get(code="La1aC1")
        stray = User.objects.get(code="l0l0oh")
        group.invites.add(stray)
        group.co_owners.add(stray)

        call_command("seed_demo", lang="en", verbosity=0)

        assert stray.code not in self._people(group, "invites")
        assert stray.code not in self._people(group, "co_owners")

    def test_two_runs_in_a_row_give_the_same_groups(self):
        call_command("seed_demo", lang="en", verbosity=0)
        self._join_real_people()
        call_command("seed_demo", lang="en", verbosity=0)

        def snapshot():
            return {
                c.code: (self._people(c, "invites"), self._people(c, "co_owners"))
                for c in Collection.objects.all()
            }

        first = snapshot()
        call_command("seed_demo", lang="en", verbosity=0)

        assert snapshot() == first
