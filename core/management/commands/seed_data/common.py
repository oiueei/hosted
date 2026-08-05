"""
Structural demo-data skeleton shared across all language variants.

Only fields that DON'T change between languages live here (codes, types,
ownership, relationships, flags, prices, image ids, tags, …). The translatable
text for each entity lives in the per-locale modules (en.py, es.py) and is
merged onto this skeleton by `seed_demo.load_seed_data`. Adding a language means
translating text only — never re-declaring structure (R17).

Image ids (photo/thumbnail/gallery) are stored BARE here; `seed_demo` prefixes
them with ``SEED_IMAGE_FOLDER`` (oiueei/seed/) at seed time — that's the Cloudinary
folder the demo fixtures actually live in, kept apart from real user uploads.
"""

import json
from datetime import date


def _localized_tag(**texts):
    """A tag label carrying one text per language (O6).

    The stored value is the serialized ``{lang: text}`` map. Things reference
    their collection's vocabulary **by raw string**, so each label is defined
    once as a constant below and reused byte-identically everywhere it appears.
    A label that reads the same in every language stays a plain string instead.
    """
    return json.dumps(texts, ensure_ascii=False)


# Lili's lending library vocabulary.
TAG_COCINA = _localized_tag(es="Cocina", ca="Cuina", en="Kitchen")
TAG_JARDIN = _localized_tag(es="Jardín", ca="Jardí", en="Garden")
TAG_BRICOLAJE = _localized_tag(es="Bricolaje", ca="Bricolatge", en="DIY")
TAG_CRIANZA = _localized_tag(es="Crianza", ca="Criança", en="Parenting")
TAG_HOGAR = _localized_tag(es="Hogar", ca="Llar", en="Home")
TAG_LIMPIEZA = _localized_tag(es="Limpieza", ca="Neteja", en="Cleaning")
TAG_DEPORTE = _localized_tag(es="Deporte", ca="Esport", en="Sports")
TAG_OCIO = _localized_tag(es="Ocio", ca="Lleure", en="Leisure")
TAG_ELECTRONICA = _localized_tag(es="Electrónica", ca="Electrònica", en="Electronics")

USERS = [
    {
        "code": "La1aN1",
        "email": "lala@mail.com",
        "name": "Lala",
        "theeeme_id": "BUU331",
        "photo": "La1aPH",
    },
    {
        "code": "L3L3oo",
        "email": "lele@mail.com",
        "name": "Lele",
        "theeeme_id": "K0P4R1",
        "photo": "L3L3PH",
    },
    {
        "code": "l1l13S",
        "email": "lili@mail.com",
        "name": "Lili",
        "theeeme_id": "BUU331",
        "photo": "l1l1PH",
    },
    {
        "code": "l0l0oh",
        "email": "lolo@mail.com",
        "name": "Lolo",
        "theeeme_id": "BUU331",
        "photo": "l0l0PH",
    },
    {
        "code": "1u1ucs",
        "email": "lulu@mail.com",
        "name": "Lulu",
        "theeeme_id": "BUU331",
        "photo": "1u1uPH",
    },
]

COLLECTIONS = [
    {
        "code": "La1aC1",
        "owner_code": "La1aN1",
        "visibility": "PRIVATE",
        "invites": ["L3L3oo"],
        "is_onboarding": True,
        "allowed_thing_types": ["SELL_THING"],
        "thumbnail": "La1aC1",
    },
    {
        "code": "l0l0C1",
        "owner_code": "l0l0oh",
        "visibility": "PUBLIC",
        "invites": ["La1aN1", "l1l13S", "L3L3oo", "1u1ucs"],
        "is_onboarding": True,
        "allowed_thing_types": ["GIFT_THING"],
        "thumbnail": "L3L3C2",
    },
    {
        "code": "l1l1C1",
        "owner_code": "l1l13S",
        "visibility": "PUBLIC",
        "invites": ["La1aN1", "L3L3oo", "l0l0oh"],
        "is_onboarding": True,
        "allowed_thing_types": ["RENT_THING"],
        "tags": [
            TAG_COCINA,
            TAG_JARDIN,
            TAG_BRICOLAJE,
            TAG_CRIANZA,
            TAG_HOGAR,
            TAG_LIMPIEZA,
            TAG_DEPORTE,
            TAG_OCIO,
            TAG_ELECTRONICA,
        ],
        "thumbnail": "l1l1C1",
    },
]

THINGS = [
    {
        "code": "La1a01",
        "type": "SELL_THING",
        "owner_code": "La1aN1",
        "collections": ["La1aC1"],
        "thumbnail": "La1a01_a",
        "gallery": ["La1a01_b"],
        "fee": "10.00",
        "condition": "NEW",
    },
    {
        "code": "La1a02",
        "type": "SELL_THING",
        "owner_code": "La1aN1",
        "collections": ["La1aC1"],
        "thumbnail": "La1a02",
        "fee": "10.00",
        "availability": "IMMEDIATE",
    },
    {
        "code": "La1a03",
        "type": "SELL_THING",
        "owner_code": "La1aN1",
        "collections": ["La1aC1"],
        "thumbnail": "La1a03",
        "fee": "10.00",
        "condition": "GOOD",
        "availability": "NEXT_WEEK",
    },
    {
        "code": "La1a04",
        "type": "SELL_THING",
        "owner_code": "La1aN1",
        "collections": ["La1aC1"],
        "thumbnail": "La1a04",
        "fee": "10.00",
        "availability": "IMMEDIATE",
        "location": "Barcelona",
    },
    {
        "code": "La1a05",
        "type": "SELL_THING",
        "owner_code": "La1aN1",
        "collections": ["La1aC1"],
        "thumbnail": "La1a05",
        "fee": "10.00",
        "condition": "NEW",
    },
    {
        "code": "l1l101",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l101",
        "fee": "1.00",
        "tags": [TAG_CRIANZA],
    },
    {
        "code": "l1l102",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l102",
        "fee": "3.00",
        "tags": [TAG_CRIANZA],
    },
    {
        "code": "l1l103",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l103",
        "fee": "1.00",
        "tags": [TAG_OCIO, TAG_CRIANZA],
    },
    {
        "code": "l1l104",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l104",
        "fee": "5.00",
        "tags": [TAG_CRIANZA, TAG_JARDIN],
    },
    {
        "code": "l1l105",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l105",
        "fee": "1.00",
        "tags": [TAG_CRIANZA],
    },
    {
        "code": "l1l106",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l106",
        "fee": "3.00",
        "tags": [TAG_JARDIN],
    },
    {
        "code": "l1l107",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l107",
        "fee": "3.00",
        "tags": [TAG_ELECTRONICA],
    },
    {
        "code": "l1l108",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l108",
        "fee": "3.00",
        "tags": [TAG_OCIO, TAG_ELECTRONICA],
    },
    {
        "code": "l1l109",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l109",
        "fee": "1.00",
        "tags": [TAG_LIMPIEZA],
    },
    {
        "code": "l1l110",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l110",
        "fee": "3.00",
        "tags": [TAG_LIMPIEZA],
    },
    {
        "code": "l1l111",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l111",
        "fee": "5.00",
        "tags": [TAG_LIMPIEZA],
    },
    {
        "code": "l1l112",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l112",
        "fee": "3.00",
        "tags": [TAG_BRICOLAJE],
    },
    {
        "code": "l1l113",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l113",
        "fee": "3.00",
        "tags": [TAG_BRICOLAJE],
    },
    {
        "code": "l1l114",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l114",
        "fee": "1.00",
        "tags": [TAG_DEPORTE],
    },
    {
        "code": "l1l115",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l115",
        "fee": "1.00",
        "tags": [TAG_DEPORTE],
    },
    {
        "code": "l1l116",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l116",
        "fee": "1.00",
        "tags": [TAG_DEPORTE],
    },
    {
        "code": "l1l117",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l117",
        "fee": "1.00",
        "tags": [TAG_DEPORTE],
    },
    {
        "code": "l1l118",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l118",
        "fee": "5.00",
        "tags": [TAG_DEPORTE],
    },
    {
        "code": "l1l119",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l119",
        "fee": "1.00",
        "tags": [TAG_COCINA],
    },
    {
        "code": "l1l120",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l120",
        "fee": "3.00",
        "tags": [TAG_COCINA],
    },
    {
        "code": "l1l121",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l121",
        "fee": "3.00",
        "tags": [TAG_COCINA],
    },
    {
        "code": "l1l122",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l122",
        "fee": "3.00",
        "tags": [TAG_COCINA],
    },
    {
        "code": "l1l123",
        "type": "RENT_THING",
        "owner_code": "l1l13S",
        "collections": ["l1l1C1"],
        "thumbnail": "l1l123",
        "fee": "1.00",
        "tags": [TAG_COCINA],
    },
    {
        "code": "l0l001",
        "type": "GIFT_THING",
        "owner_code": "l0l0oh",
        "collections": ["l0l0C1"],
        "thumbnail": "l0l001",
        "is_endless": True,
    },
    {
        "code": "l0l002",
        "type": "GIFT_THING",
        "owner_code": "l0l0oh",
        "collections": ["l0l0C1"],
        "thumbnail": "l0l002",
        "is_endless": True,
    },
    {
        "code": "l0l003",
        "type": "GIFT_THING",
        "owner_code": "l0l0oh",
        "collections": ["l0l0C1"],
        "thumbnail": "l0l003",
        "is_endless": True,
    },
    {
        "code": "l0l004",
        "type": "GIFT_THING",
        "owner_code": "l0l0oh",
        "collections": ["l0l0C1"],
        "thumbnail": "l0l004",
        "is_endless": True,
    },
    {
        "code": "l0l005",
        "type": "GIFT_THING",
        "owner_code": "l0l0oh",
        "collections": ["l0l0C1"],
        "thumbnail": "l0l005",
        "is_endless": True,
    },
    {
        "code": "l0l006",
        "type": "GIFT_THING",
        "owner_code": "l0l0oh",
        "collections": ["l0l0C1"],
        "thumbnail": "l0l006",
        "is_endless": True,
    },
    {
        "code": "l0l007",
        "type": "GIFT_THING",
        "owner_code": "l0l0oh",
        "collections": ["l0l0C1"],
        "thumbnail": "l0l007",
        "is_endless": True,
    },
]

FAQS = [
    {
        "thing_code": "La1a01",
        "questioner_code": "L3L3oo",
    },
    {
        "thing_code": "La1a02",
        "questioner_code": "L3L3oo",
    },
    {
        "thing_code": "La1a03",
        "questioner_code": "L3L3oo",
    },
    {
        "thing_code": "La1a04",
        "questioner_code": "L3L3oo",
    },
    {
        "thing_code": "La1a05",
        "questioner_code": "L3L3oo",
    },
]

# ThingTransfer chain — (thing_code, from_code, to_code, lent_date, returned_date)
#
# Lili's lending library: a thing goes out from Lili and comes back, so each row
# is one loan. A null returned_date means it is still out — that thing renders as
# "currently with X", and its journey lists every borrower before them. Rows are
# oldest-first per thing; the model's -lent_date ordering shows the newest on top.
TRANSFERS = [
    # The drill is the library's workhorse — three borrowers, still out.
    ("l1l112", "l1l13S", "l0l0oh", date(2026, 1, 15), date(2026, 2, 2)),
    ("l1l112", "l1l13S", "La1aN1", date(2026, 3, 10), date(2026, 3, 24)),
    ("l1l112", "l1l13S", "L3L3oo", date(2026, 5, 5), None),
    # Steam cleaner — spring cleaning, both returned.
    ("l1l110", "l1l13S", "La1aN1", date(2026, 2, 20), date(2026, 2, 27)),
    ("l1l110", "l1l13S", "l0l0oh", date(2026, 4, 11), date(2026, 4, 18)),
    # Wet & dry vacuum — one long loan, back on the shelf.
    ("l1l111", "l1l13S", "L3L3oo", date(2026, 3, 1), date(2026, 3, 20)),
    # Game Boy — passed around the neighbourhood, still out.
    ("l1l108", "l1l13S", "l0l0oh", date(2026, 1, 8), date(2026, 2, 14)),
    ("l1l108", "l1l13S", "L3L3oo", date(2026, 4, 2), None),
    # Toolkit — a single afternoon.
    ("l1l113", "l1l13S", "La1aN1", date(2026, 4, 25), date(2026, 4, 26)),
    # Laser printer — the tax-return loan.
    ("l1l107", "l1l13S", "L3L3oo", date(2026, 6, 1), date(2026, 6, 8)),
]
