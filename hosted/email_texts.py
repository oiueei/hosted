"""The words this deployment sends about a request to run a group here.

**A catalogue of its own, and deliberately not three new keys in
`core/services/email_texts/`.** That directory is upstream's, it is merged from
`development` on every round, and a key added here would be a conflict on every
one of them for text the standalone has no sender for — there is no request to
answer where there is no gate.

Same shape as upstream's catalogues so it reads the same way: flat ``TEXTS``
dicts of ``str.format`` templates, English as the reference and the fallback,
`t(key, lang)` resolving one. The operator's own notice is not here — that one is
written in the sender, like `send_stats_summary_email`, because it is an ops mail
in the language of whoever runs the service rather than copy for a user.
"""

EN = {
    "approved_subject": "Your request was approved",
    "approved_intro": "We read what you sent us, and the answer is yes.",
    "approved_body": (
        "Community collections, lending and renting are available on your account "
        "from now on. Nothing else changes, and nothing you already had is affected."
    ),
    "approved_cta": "Create a collection",
    "approved_plain": (
        "We read what you sent us, and the answer is yes.\n\n"
        "Community collections, lending and renting are available on your account "
        "from now on.\n\n"
        "Create a collection: {url}\n"
    ),
    "rejected_subject": "About your request",
    "rejected_intro": "We read what you sent us, and this time the answer is no.",
    "rejected_body": (
        "Giving things away and selling them are open to you as before. "
        "You are welcome to ask again — if something has changed, or if there is "
        "more to say, that is the place to say it."
    ),
    "rejected_cta": "Ask again",
    "rejected_plain": (
        "We read what you sent us, and this time the answer is no.\n\n"
        "Giving things away and selling them are open to you as before. You are "
        "welcome to ask again if something has changed, or if there is more to say.\n\n"
        "Ask again: {url}\n"
    ),
}

ES = {
    "approved_subject": "Tu solicitud está aprobada",
    "approved_intro": "Hemos leído lo que nos escribiste, y la respuesta es sí.",
    "approved_body": (
        "A partir de ahora tienes disponibles las colecciones comunitarias, prestar "
        "y alquilar. No cambia nada más, y nada de lo que ya tenías se ve afectado."
    ),
    "approved_cta": "Crear una colección",
    "approved_plain": (
        "Hemos leído lo que nos escribiste, y la respuesta es sí.\n\n"
        "A partir de ahora tienes disponibles las colecciones comunitarias, prestar "
        "y alquilar.\n\n"
        "Crear una colección: {url}\n"
    ),
    "rejected_subject": "Sobre tu solicitud",
    "rejected_intro": "Hemos leído lo que nos escribiste, y esta vez la respuesta es no.",
    "rejected_body": (
        "Regalar y vender siguen disponibles para ti, igual que antes. Puedes volver "
        "a pedirlo cuando quieras: si algo ha cambiado, o si hay algo más que contar, "
        "ese es el sitio para decirlo."
    ),
    "rejected_cta": "Volver a pedirlo",
    "rejected_plain": (
        "Hemos leído lo que nos escribiste, y esta vez la respuesta es no.\n\n"
        "Regalar y vender siguen disponibles para ti, igual que antes. Puedes volver "
        "a pedirlo si algo ha cambiado, o si hay algo más que contar.\n\n"
        "Volver a pedirlo: {url}\n"
    ),
}

CA = {
    "approved_subject": "La teva sol·licitud està aprovada",
    "approved_intro": "Hem llegit el que ens vas escriure, i la resposta és sí.",
    "approved_body": (
        "A partir d'ara tens disponibles les col·leccions comunitàries, deixar i "
        "llogar. No canvia res més, i res del que ja tenies no es veu afectat."
    ),
    "approved_cta": "Crear una col·lecció",
    "approved_plain": (
        "Hem llegit el que ens vas escriure, i la resposta és sí.\n\n"
        "A partir d'ara tens disponibles les col·leccions comunitàries, deixar i "
        "llogar.\n\n"
        "Crear una col·lecció: {url}\n"
    ),
    "rejected_subject": "Sobre la teva sol·licitud",
    "rejected_intro": "Hem llegit el que ens vas escriure, i aquesta vegada la resposta és no.",
    "rejected_body": (
        "Regalar i vendre continuen disponibles per a tu, igual que abans. Pots "
        "tornar a demanar-ho quan vulguis: si alguna cosa ha canviat, o si hi ha "
        "res més a dir, aquest és el lloc per dir-ho."
    ),
    "rejected_cta": "Tornar a demanar-ho",
    "rejected_plain": (
        "Hem llegit el que ens vas escriure, i aquesta vegada la resposta és no.\n\n"
        "Regalar i vendre continuen disponibles per a tu, igual que abans. Pots "
        "tornar a demanar-ho si alguna cosa ha canviat, o si hi ha res més a dir.\n\n"
        "Tornar a demanar-ho: {url}\n"
    ),
}

TEXTS = {"en": EN, "es": ES, "ca": CA}


def t(key, lang=None):
    """The text for ``key`` in ``lang``, falling back to English.

    Mirrors ``core.services.email_texts.T``: an unknown language or a missing key
    lands on the English catalogue rather than raising, because the alternative
    is a ``KeyError`` in the middle of an operator's approval — after the row has
    already been resolved.
    """
    return TEXTS.get(lang or "en", EN).get(key) or EN[key]
