// Full legal text for the www.oiueei.com deployment. The standalone repo ships
// the generic version; this file replaces it here. The operator's identity is
// injected from VITE_LEGAL_OPERATOR / _NIF / _ADDRESS at build time (Vite
// static replacement — see frontend/scripts/check-legal-env.mjs), so the NIF
// and postal address are never committed as source.
export default `
# Our commitment

OIUEEI runs without ads and without third-party analytics: nobody tracks you while you use it. Your data is not the product — it is never sold or shared with anyone. There are no tracking pixels in the emails and no links wrapped in trackers. This commitment is written into the project's design rules; it's the starting point, not the fine print.

# Legal notice

In compliance with Spanish Law 34/2002 (LSSI-CE), the owner of www.oiueei.com is:

**${import.meta.env.VITE_LEGAL_OPERATOR}** — Spanish tax ID (NIF) ${import.meta.env.VITE_LEGAL_NIF} — ${import.meta.env.VITE_LEGAL_ADDRESS} — contact: legal@oiueei.com.

OIUEEI is a personal project: there is no company behind it. I am its creator, maintainer and the person responsible.

# Privacy policy

**Data controller:** the owner named in the Legal notice.

**What I process, why, and on what basis:**

- **Email and name** — your account and the magic sign-in links (no passwords), plus the service's own notices. Basis: performance of the service (art. 6.1.b GDPR).
- **Optional profile** (bio, photo, language) — whatever you choose to show. Basis: performance of the service.
- **Optional demographics** (birth-year generation and postal code) — visible only to the people who run your communities, in aggregate; never public. Basis: your consent (art. 6.1.a); withdraw it by clearing the fields.
- **The content you publish** (collections, things and their photos, questions and answers, requests) — the service itself. Basis: performance of the service.
- **Technical records** (IP address in security logs and rate limits) — protecting the service from abuse. Basis: legitimate interest (art. 6.1.f).
- **First-party pseudonymised metrics** — aggregate counts to operate the service; they never leave our database and are never shared. Basis: legitimate interest.
- **Emails:** the essential ones (sign-in, invitations) are always sent; activity emails can be turned off; news emails are only sent if you turn them on (art. 6.1.a).

**Processors:** Heroku/Salesforce (hosting, servers in Ireland; US company), Hetzner Online GmbH (images and documents, Germany), Mailgun/Sinch (email delivery, European region), Sentry/Functional Software (error monitoring, data hosted in the European region, Germany — events are scrubbed of personal data before being sent) and Tally (the feedback form, Belgium — it receives nothing unless you write in it). Transfers to the USA rely on the EU-US Data Privacy Framework and/or standard contractual clauses.

**What there isn't:** advertising, third-party analytics, sale or sharing of data, automated decisions or profiling. **Cookies and local storage:** technical only. The cookies are session and security; your browser also keeps your user code, your language and appearance preferences, and whether you have seen the welcome. None of it needs consent, which is why there is no banner.

**For how long:** as long as your account exists. You can **delete your account yourself** (Edit profile → Delete account, with email confirmation): it is immediate and irreversible — your account, your collections, your things and their photos, and your requests are erased. Questions you asked on other people's things and the transfer history stay without your name ("Former member"). Backups are taken daily and rotate on their own: anything older than a week is gone.

**Your rights:** access, rectification, erasure and portability you exercise directly from your profile: you can download all your data in one file whenever you like and, if you run a group, the whole group as well — that second file carries other people's data, so keep it safe. For objection or restriction write to legal@oiueei.com. You may also lodge a complaint with the Spanish Data Protection Agency (www.aepd.es).

**If you arrived through an invitation:** your email address was given to us by whoever invited you, and it is used only to send you that invitation. If you do not accept it and nobody invites you again, that pending account deletes itself after 60 days.

**Minors:** if you are under 14, you need your guardians' permission to use OIUEEI.

**Looking for a quick answer?** The [frequently asked questions](/faq) say the same in plain language. This page is the full version, and the one that counts.

# Terms and conditions

1. **What it is.** OIUEEI is a platform for sharing things between people who know each other. It is in **alpha**: nothing is finished and you will find rough edges.
2. **Your account.** You sign in with magic links by email; use an address you can read. You can delete your account at any time, from your profile.
3. **Price.** While OIUEEI is in testing (alpha and beta) the service is **free**, and accounts created during this stage stay free. A paid plan for new accounts is planned for later; prices will be announced here, and in these terms, with notice, before anywhere else.
4. **Continuity.** The tools to export your data already exist: from your profile, whenever you like, yours in one file and — if you run a group — the whole group (its things, its members, the history). If OIUEEI were ever to close, I will give at least **90 days' notice**, ample time to move it to another platform or self-host the application from GitHub (the licence allows it).
5. **Your content.** It is yours and you are responsible for it. Don't publish anything illegal, harmful or that isn't yours to publish. There is a report button, and I may remove content that breaks these rules.
6. **Between people.** Exchanges (gifts, sales, loans, rentals) are agreements between users: OIUEEI is not a party to them, processes no payments and does not guarantee transactions. A **deposit** written on a listing is information the two people agree between themselves: OIUEEI does not charge it, hold it, move it, or guarantee that it comes back.
7. **Warranties.** The service is provided "as is", without warranties, to the extent the law allows. Nothing here limits the rights the law grants you as a consumer.
8. **Changes.** If these terms change, I will give reasonable notice.
9. **Law and venue.** Spanish law; for any dispute, the courts of Barcelona, unless as a consumer you are entitled to the courts of your own domicile.

# The code

OIUEEI is open source software under the **EUPL-1.2**, a strong copyleft licence: you can read it, modify it and self-host it in production, including as a service. What the licence asks in return is reciprocity — run a modified OIUEEI as a network service and its source is owed to your users under the same licence; an unmodified deployment owes nothing beyond keeping the notices. The project lives on GitHub (github.com/oiueei/standalone).

---

*Last updated: 3 September 2026.*
`;
