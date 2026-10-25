"""The app's own palette: one row in the database, edited in the admin.

Its colours are hex and live in a table, so `paletteContrast.test.js` cannot see
them. What that test asks of the twelve collection palettes is therefore asked
here, when the row is saved — and these tests are what make that promise more than
a docstring.
"""

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from core.models import Braaanding, Theeeme
from core.models.braaanding import (
    BRAAANDING_CODE,
    CACHE_SECONDS,
    DEFAULT_COLORS,
    braaanding,
    forget_braaanding,
)
from core.services.palette_contrast import contrast_failures, contrast_ratio

SEED = {
    "color_01": "#191919",
    "color_02": "#F4E5DD",
    "color_03": "#D77452",
    "color_04": "#191919",
    "color_05": "#191919",
    "color_06": "#FAFAFA",
}


@pytest.mark.django_db
class TestTheRowTheMigrationSeeds:
    def test_exactly_one_row_exists_after_migrating_with_the_initial_values(self):
        rows = Braaanding.objects.all()

        assert rows.count() == 1
        row = rows.get()
        assert row.pk == BRAAANDING_CODE
        assert row.colors == SEED
        assert row.koro == "basic"

    def test_it_is_not_a_row_of_the_collections_palettes(self):
        """No curator can pick it, and a new collection can never draw it at random."""
        assert not Theeeme.objects.filter(color_01__startswith="#").exists()
        assert Braaanding._meta.db_table == "braaanding"
        assert Braaanding._meta.db_table != Theeeme._meta.db_table

    def test_the_seed_is_itself_readable_enough_to_paint_with(self):
        assert contrast_failures(SEED) == []


class TestContrastMatchesTheMeasuredValues:
    """The ratios measured when the palette was chosen, so the formula is not
    merely agreeing with itself."""

    @pytest.mark.parametrize(
        ("foreground", "background", "expected"),
        [
            ("#FAFAFA", "#191919", 16.8),  # primary button label on its fill
            ("#191919", "#F4E5DD", 14.3),  # body text on the page
            ("#191919", "#FFFFFF", 17.6),  # secondary button / links on white
            ("#191919", "#D77452", 5.45),  # hero text on the hero
        ],
    )
    def test_ratio(self, foreground, background, expected):
        assert contrast_ratio(foreground, background) == pytest.approx(expected, abs=0.05)

    def test_black_on_white_is_the_maximum_21(self):
        assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)


@pytest.mark.django_db
class TestASavedPaletteHasToBeReadable:
    def _row(self, **changes):
        row = Braaanding.objects.get()
        for field, value in changes.items():
            setattr(row, field, value)
        return row

    @pytest.mark.parametrize("bad", ["red", "#FFF", "#GGGGGG", "191919", "#1919190", ""])
    def test_a_malformed_hex_is_rejected(self, bad):
        row = self._row(color_03=bad)

        with pytest.raises(ValidationError) as caught:
            row.full_clean()

        assert "color_03" in caught.value.message_dict

    @pytest.mark.parametrize(
        ("change", "pairing"),
        [
            ({"color_06": "#222222"}, "primary button"),  # label dark on a dark fill
            ({"color_02": "#202020"}, "body text"),  # page as dark as the text
            ({"color_05": "#D77452"}, "hero text"),  # hero text the colour of the hero
            ({"color_04": "#BBBBBB"}, "secondary button and links"),  # pale on white
            ({"color_02": "#A04030", "color_04": "#000000"}, "front door warning"),
        ],
    )
    def test_a_palette_that_fails_a_contrast_is_rejected_and_names_it(self, change, pairing):
        row = self._row(**change)

        with pytest.raises(ValidationError) as caught:
            row.full_clean()

        assert pairing in " ".join(caught.value.messages)

    def test_a_readable_change_is_accepted(self):
        row = self._row(color_03="#E0B090", koro="wave")

        row.full_clean()
        row.save()

        assert braaanding()["color_03"] == "#E0B090"

    def test_the_admin_form_refuses_what_the_model_refuses(self):
        """The guard has to be where the values are changed: the admin."""
        model_admin = admin.site._registry[Braaanding]
        request = RequestFactory().get("/")
        form_class = model_admin.get_form(request)
        data = {**SEED, "koro": "basic", "color_06": "#222222"}

        form = form_class(data=data, instance=Braaanding.objects.get())

        assert not form.is_valid()
        assert "primary button" in " ".join(form.non_field_errors())

    def test_the_admin_adds_and_deletes_nothing(self):
        model_admin = admin.site._registry[Braaanding]
        request = RequestFactory().get("/")

        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_delete_permission(request, Braaanding.objects.get()) is False


@pytest.mark.django_db
class TestTheHelperAndItsCache:
    def test_it_answers_the_row_as_colours_and_koro(self):
        assert braaanding() == {**SEED, "koro": "basic"}

    def test_saving_the_row_drops_the_remembered_answer(self):
        assert braaanding()["color_03"] == "#D77452"  # now remembered

        row = Braaanding.objects.get()
        row.color_03 = "#E0B090"
        row.save()

        assert braaanding()["color_03"] == "#E0B090"

    def test_a_second_call_does_not_read_the_row_again(self, django_assert_num_queries):
        braaanding()  # remembers it

        with django_assert_num_queries(0):
            braaanding()

    def test_a_worker_forgets_it_after_a_minute_so_another_workers_edit_arrives(self, monkeypatch):
        """The memory is per process: a save in another worker cannot clear this one,
        so what bounds the staleness is the time."""
        clock = [1000.0]
        monkeypatch.setattr("core.models.braaanding.time.monotonic", lambda: clock[0])
        forget_braaanding()  # what was remembered was stamped by the real clock
        assert braaanding()["color_03"] == "#D77452"
        # Another worker's save: the row changes, no signal reaches this process.
        Braaanding.objects.filter(pk=BRAAANDING_CODE).update(color_03="#E0B090")

        clock[0] += CACHE_SECONDS - 1
        assert braaanding()["color_03"] == "#D77452"
        clock[0] += 2
        assert braaanding()["color_03"] == "#E0B090"

    def test_the_answer_is_a_copy_nobody_can_corrupt_the_memory_through(self):
        braaanding()["color_01"] = "#000000"

        assert braaanding()["color_01"] == "#191919"

    def test_without_a_row_the_defaults_answer(self):
        Braaanding.objects.all().delete()

        assert braaanding() == {**DEFAULT_COLORS, "koro": "basic"}
