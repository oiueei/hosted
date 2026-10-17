# ruff: noqa: E501  -- the lines are copied word for word; their length is their text's.
"""The growth line at the foot of an email, chosen for the person who reads it.

Core ends every email with one line inviting its reader to start something of their
own, and links it to the form of the kind it talks about. That is right where
everybody can do everything. Here some of it has to be asked for first, so a line
that says "open a library" would send an account that may not yet to a form that
refuses it. This module is what ``VIRAL_LINE_PROVIDER`` points at: it picks one of
the fifteen lines below at random and sends the recipient to **the place where they
can act on it** — the form when this deployment lets them, otherwise the page that
explains how to ask for exactly what is missing (``/access/<need>``).

The destination is decided on the server, per recipient, from the same
``capabilities`` the product reads everywhere, so what the email offers is what the
API would accept. Links are plain paths: no redirect, no tracker (DESIGN §9).
"""

import random

from core.models.collection import KIND_THING_TYPES
from core.services.creator_policy import capabilities_for

DEFAULT_LANG = "es"
LANGS = ("es", "ca", "en")


def _line(kind, paid, community, es, ca, en):
    """One line: what it needs of the recipient, and its text in each language."""
    return {
        "need": {"kind": kind, "paid": paid, "community": community},
        "es": {"text": es[0], "cta": es[1]},
        "ca": {"text": ca[0], "cta": ca[1]},
        "en": {"text": en[0], "cta": en[1]},
    }


LINES = [
    _line(
        "STALL",
        False,
        False,
        (
            "¿Renuevas el armario? Abre un rastrillo con la ropa que ya no usas y ofrécela a tus amigos.",
            "Empieza aquí",
        ),
        (
            "Renoves l'armari? Obre una paradeta amb la roba que ja no fas servir i ofereix-la als teus amics.",
            "Comença aquí",
        ),
        (
            "Refreshing your wardrobe? Open a stall with the clothes you no longer wear and offer them to your friends.",
            "Start here",
        ),
    ),
    _line(
        "STALL",
        False,
        False,
        (
            "¿Estanterías llenas de libros ya leídos? Ponlos en un rastrillo y dales una segunda vida.",
            "Así de fácil",
        ),
        (
            "Prestatges plens de llibres ja llegits? Posa'ls en una paradeta i dona'ls una segona vida.",
            "Així de fàcil",
        ),
        (
            "Shelves full of books you've already read? Put them in a stall and give them a second life.",
            "It's that easy",
        ),
    ),
    _line(
        "STALL",
        False,
        False,
        (
            "¿Juguetes que se han quedado pequeños? Abre un rastrillo y pásalos a otras familias.",
            "Crea el tuyo",
        ),
        (
            "Joguines que s'han quedat petites? Obre una paradeta i passa-les a altres famílies.",
            "Crea la teva",
        ),
        (
            "Toys they've outgrown? Open a stall and pass them on to other families.",
            "Create yours",
        ),
    ),
    _line(
        "STALL",
        False,
        False,
        (
            "¿Mudanza a la vista? Abre un rastrillo con lo que no te llevas y encuéntrale una nueva casa.",
            "Empieza por aquí",
        ),
        (
            "Et mudes aviat? Obre una paradeta amb el que no t'enduràs i troba-li una nova llar.",
            "Comença per aquí",
        ),
        (
            "Moving soon? Open a stall with what you're not taking and find it a new home.",
            "Start here",
        ),
    ),
    _line(
        "STALL",
        False,
        False,
        (
            "¿Se acumulan cosas en la oficina? Abre un rastrillo solo de regalos y que se las quede quien las necesite.",
            "Empieza a regalar",
        ),
        (
            "S'acumulen coses a l'oficina? Obre una paradeta només de regals i que se les quedi qui les necessiti.",
            "Comença a regalar",
        ),
        (
            "Stuff piling up at the office? Open a gift-only stall and let whoever needs it take it.",
            "Start giving",
        ),
    ),
    _line(
        "STALL",
        False,
        True,
        (
            "¿En tu edificio hay cosas que ya nadie usa? Monta un rastrillo de vecinos donde cada uno ponga lo suyo.",
            "Monta el rastrillo",
        ),
        (
            "Al teu edifici hi ha coses que ja no fa servir ningú? Munta una paradeta de veïns on cadascú posi el que és seu.",
            "Munta la paradeta",
        ),
        (
            "Things nobody in your building uses anymore? Set up a neighbours' stall where everyone puts in their own.",
            "Set up the stall",
        ),
    ),
    _line(
        "LIBRARY",
        False,
        False,
        (
            "¿Un taladro que usas dos veces al año? Abre una biblioteca de las cosas con tus herramientas y préstalas a tus vecinos.",
            "Abre tu biblioteca",
        ),
        (
            "Un trepant que fas servir dues vegades l'any? Obre una biblioteca de les coses amb les teves eines i deixa-les als teus veïns.",
            "Obre la teva biblioteca",
        ),
        (
            "A drill you use twice a year? Open a library of things with your tools and lend them to your neighbours.",
            "Open your library",
        ),
    ),
    _line(
        "LIBRARY",
        True,
        False,
        (
            "¿Cámaras, objetivos o equipo que pasan más tiempo guardados que trabajando? Alquílalos en una biblioteca de las cosas y que te los pidan por días.",
            "Quiero alquilarlos",
        ),
        (
            "Càmeres, objectius o equip que passen més temps guardats que treballant? Lloga'ls en una biblioteca de les coses i que te'ls demanin per dies.",
            "Vull llogar-los",
        ),
        (
            "Cameras, lenses or gear that spend more time in storage than at work? Rent them out from a library of things and let people ask for them by the day.",
            "Rent them out",
        ),
    ),
    _line(
        "LIBRARY",
        True,
        False,
        (
            "¿Un local o un estudio lleno de máquinas y herramientas que no usas cada día? Alquila el equipo y que te lo pidan por días.",
            "Alquila tu equipo",
        ),
        (
            "Un local o un estudi ple de màquines i eines que no fas servir cada dia? Lloga l'equip i que te'l demanin per dies.",
            "Lloga el teu equip",
        ),
        (
            "A studio or a unit full of machines and tools you don't use every day? Rent out the gear and let people ask for it by the day.",
            "Rent out your gear",
        ),
    ),
    _line(
        "SHED",
        False,
        False,
        (
            "¿Un espacio maker con impresoras 3D, Arduinos y otros equipos? Abre un taller y que cada maker reserve su turno sin líos por WhatsApp.",
            "Organiza los turnos",
        ),
        (
            "Un espai maker amb impressores 3D, Arduinos i altres equips? Obre un taller i que cada maker reservi el seu torn sense embolics per WhatsApp.",
            "Organitza els torns",
        ),
        (
            "A makerspace with 3D printers, Arduinos and other gear? Open a shed and let every maker book their slot without the WhatsApp chaos.",
            "Organise the slots",
        ),
    ),
    _line(
        "SHED",
        False,
        False,
        (
            "¿Una sala, una impresora o un banco de trabajo que usáis entre varios? Abre un taller y reservad por turnos.",
            "Abre un taller",
        ),
        (
            "Una sala, una impressora o un banc de treball que feu servir entre diversos? Obre un taller i reserveu per torns.",
            "Obre un taller",
        ),
        (
            "A room, a printer or a workbench several of you share? Open a shed and book it in turns.",
            "Open a shed",
        ),
    ),
    _line(
        "SHED",
        False,
        False,
        (
            "¿Una cooperativa con máquinas o espacios para sus socios? Abre un taller donde cada socio reserve lo que necesita.",
            "Abre el taller",
        ),
        (
            "Una cooperativa amb màquines o espais per als seus socis? Obre un taller on cada soci reservi el que necessita.",
            "Obre el taller",
        ),
        (
            "A co-op with machines or spaces for its members? Open a shed where each member books what they need.",
            "Open the shed",
        ),
    ),
    _line(
        "STALL",
        False,
        True,
        (
            "¿Tienes una tienda y tus clientes coleccionan? Ábreles un rastrillo donde cada uno venda sus piezas.",
            "Abre un rastrillo para tus clientes",
        ),
        (
            "Tens una botiga i els teus clients col·leccionen? Obre'ls una paradeta on cadascú vengui les seves peces.",
            "Obre una paradeta per als teus clients",
        ),
        (
            "Have a shop whose customers collect things? Open them a stall where each one sells their own pieces.",
            "Open a stall for your customers",
        ),
    ),
    _line(
        "LIBRARY",
        False,
        True,
        (
            "¿Un grupo de amigos que comparte libros, juegos o lo que sea? Abrid una biblioteca de las cosas donde cada uno ponga lo suyo, con vuestras propias normas.",
            "Abrid vuestra biblioteca",
        ),
        (
            "Un grup d'amics que comparteix llibres, jocs o el que sigui? Obriu una biblioteca de les coses on cadascú posi el que és seu, amb les vostres pròpies normes.",
            "Obriu la vostra biblioteca",
        ),
        (
            "A group of friends sharing books, games or anything else? Open a library of things where everyone puts in their own, with your own rules.",
            "Open your library",
        ),
    ),
    _line(
        None,
        False,
        False,
        (
            "¿Un grupo de amigos, un edificio, un equipo? Elige rastrillo, biblioteca de las cosas o taller y compartid lo vuestro.",
            "Crea tu colección",
        ),
        (
            "Un grup d'amics, un edifici, un equip? Tria paradeta, biblioteca de les coses o taller i compartiu el que és vostre.",
            "Crea la teva col·lecció",
        ),
        (
            "A group of friends, a building, a team? Pick a stall, a library of things or a shed and share what's yours.",
            "Create your collection",
        ),
    ),
]


def destination(need, capabilities):
    """Where a recipient with these ``capabilities`` acts on a line with this ``need``.

    The form of the kind when everything the line asks for is open to them; if not,
    ``/access/<what is missing>``, the most specific first — a community, then
    renting, then the kind itself. Renting goes before the kind on purpose: someone
    who lacks the whole library also lacks renting, and "I want to rent" has to
    measure interest in renting, not in lending.
    """
    kind = need["kind"]
    if need["community"] and "COMMUNITY" not in capabilities.collection_modes:
        return "/access/community"
    if kind is None:
        return "/new"
    if need["paid"]:
        paid_verb = KIND_THING_TYPES[kind][-1]
        if paid_verb not in capabilities.thing_types:
            return "/access/rent"
    if kind not in capabilities.collection_kinds:
        return f"/access/{kind.lower()}"
    return f"/{kind.lower()}/new"


def pick_line(user, lang):
    """The ``VIRAL_LINE_PROVIDER`` function: one line, with a destination for ``user``.

    ``user`` is the recipient's ``User``, or ``None`` for an address with no account,
    which is treated as the visitor who has not asked for anything. The deployment's
    policy is asked once, so a send costs at most one query more.
    """
    line = random.choice(LINES)
    texts = line[lang if lang in LANGS else DEFAULT_LANG]
    return {
        "text": texts["text"],
        "cta": texts["cta"],
        "path": destination(line["need"], capabilities_for(user)),
    }
