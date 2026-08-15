# Running OIUEEI yourself, and running it for others

This repository is the whole product. Clone it, point it at a database, and you
have OIUEEI: collections, things, the four verbs, invitations, magic links,
digests, the loan chain. Nothing is held back to be sold to you later.

What it does **not** contain is the layer a particular operator wraps around it
to run OIUEEI as a service for strangers: an open sign-up door, a queue of
people asking to be allowed to lend, a subscription. That layer is where an
operator's judgement lives — who gets in, on what terms, and what a "no" says —
and it differs for every one of them. Shipping ours would give you rules to
delete before you could use your own.

So the **mechanism** is here and the **policy** is not. This document is the
list of places a deployment plugs into, and the guarantee that comes with them:
you never have to edit a file this repository also edits.

That guarantee is the whole design. A deployment that patches `config/urls.py`
or a serializer inherits a merge conflict on every update, forever, and
eventually stops updating. Everything below exists so a deployment adds files
of its own instead.

---

## 1. `DEPLOYMENT_URLCONFS` — routes of your own

A comma-separated list of dotted paths to Django URLconf modules, mounted at the
root:

```bash
DEPLOYMENT_URLCONFS=operator.urls,intranet.urls
```

```python
# operator/urls.py
from django.urls import path
from . import views

urlpatterns = [path("request-access/", views.RequestAccess.as_view())]
```

They mount **before** the SPA catch-all, and that ordering is the point. The
catch-all matches everything outside `static/`, `api/` and the admin prefix, so
a page registered after it is answered with `index.html` and a **200** — the
wrong page under a success status, which is harder to notice than a 404 because
nothing about it looks broken.

Upstream ships none: every route the product serves is already in `core.urls`.

## 2. `CREATOR_POLICY` — who may create what

A dotted path to a class, the way `AUTH_USER_MODEL` is a dotted path to a model:

```bash
CREATOR_POLICY=operator.policy.VettedCreatorPolicy
```

```python
# operator/policy.py
from core.models import Collection, Thing
from core.services.creator_policy import Capabilities, CreatorPolicy


class VettedCreatorPolicy(CreatorPolicy):
    """Giving and selling are open; anything that comes back is vetted."""

    def capabilities(self, user):
        vetted = CreatorValidation.objects.filter(user=user, approved=True).exists()
        if vetted:
            return Capabilities(
                collection_modes=tuple(Collection.Mode.values),
                thing_types=tuple(Thing.Type.values),
            )
        return Capabilities(
            collection_modes=(Collection.Mode.PROPRIETARY,),
            thing_types=(Thing.Type.GIFT_THING, Thing.Type.SELL_THING),
            request_url="https://example.org/request-access/",
        )
```

The default, `core.services.creator_policy.OpenCreatorPolicy`, says **yes to
everyone, always** — an account is the only requirement to open a collection in
either mode or offer a thing under any of the four verbs. That is OIUEEI as a
product, and it is what an upstream checkout runs.

A subclass overrides **one method**. `allows_collection_mode()` and
`allows_thing_type()` are derived from it, so a policy cannot enforce something
it does not advertise — which is the failure mode of every gate written twice.

Enforced at five doors: collection create and update, thing create and update,
and the bulk CSV import. The two edit paths only judge a **change**, so
narrowing a deployment never freezes what people already own — an owner who
could no longer fix a typo on their own lending collection would be the product
punishing them for a decision they had no part in.

## 3. `capabilities` on `GET /auth/me/` — what the UI is told

The same policy, served to the frontend on the endpoint the app already calls on
every load:

```json
"capabilities": {
  "collection_modes": ["PROPRIETARY", "COMMUNITY"],
  "thing_types": ["GIFT_THING", "SELL_THING", "RENT_THING", "LEND_THING"],
  "request_url": null
}
```

The forms build their options from this, so a narrowed deployment stops offering
what its API would refuse instead of letting someone fill a form in and meet a
403 at the end of it. Where something *is* withheld, a quiet line names it and —
if `request_url` is set — links to where it is requested.

`request_url: null` means there is nowhere to ask, and the copy changes
accordingly: "not available here" rather than "ask over there". Both messages
are generic, both live upstream, and neither ever renders under the default
policy, because nothing is withheld.

## 4. `frontend/src/deployment/` — pages, doors and copy of your own

A directory a deployment **replaces wholesale**:

```js
export const deploymentRoutes = [
  { path: '/join', Component: lazy(() => import('./JoinPage')) },
];

export const popInPath = '/join';        // the "new here?" button on /login
export const aboutPath = '/about';       // the footer's "what this is" link

export const deploymentI18n = {
  en: { join: { title: 'Come and see' } },
  es: { join: { title: 'Pásate a vernos' } },
};
```

Upstream exports the empty values: no extra routes, no open door, no about page,
no extra copy. `App.jsx`, `LoginPage.jsx`, `SiteFooter.jsx`, `CollectionPage.jsx`
and `VerifyPage.jsx` read them and are **byte-identical in both**.

`deploymentI18n` is deep-merged into the `translation` namespace every time a
language file lands, so a deployment's strings stay out of
`i18n/locales/*.json` — three files upstream edits constantly.

---

## What upstream deliberately does not have

- **No open sign-up.** `POST /auth/join/` creates nothing without a valid share
  token or PUBLIC collection code. An account exists because somebody chose to
  admit a specific person.
- **No "what this is" page.** What OIUEEI is belongs in this README; what *your*
  deployment is belongs to you (`aboutPath`).
- **No product-stats report.** The `Event` log and `DailyActivity` are written as
  always — they are product instrumentation — but what you ask them is yours.

If you want an open door, `is_onboarding` is still on `Collection` and
`seed_demo` still sets it: a view of your own, mounted through
`DEPLOYMENT_URLCONFS`, can create the account and join it to every collection
carrying that flag. The column, the flag and the landing contract
(`landing: "welcome"` on a targetless magic link) are all still here, working,
waiting for a door you write.

## Licence, and the honest version of "auditable"

OIUEEI is **source-available**, not open source: BUSL 1.1, converting to MIT in
2030 (see `LICENSE`). You may run it, modify it, and self-host it for your own
community today; what the licence reserves is offering it commercially as a
service.

Every line of the **product** is in this repository and can be read, audited and
changed. An operator's **service layer** — their sign-up door, their vetting
queue, their billing — is not part of what is distributed, and saying otherwise
would be a claim this repository cannot back. What that layer may and may not do
is bounded by what it plugs into, and that is exactly the four points above.
