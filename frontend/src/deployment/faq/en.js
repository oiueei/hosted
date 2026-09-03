/**
 * The help page's questions and answers, in English.
 *
 * Same `id`s and the same order as `es.js`, which is where the shape and the
 * rules are documented. The `id`s stay in Spanish like every other code in this
 * repo, and they are **public URLs**: `/faq#precio` reaches this answer in all
 * three languages, and a translation that renamed one would break links already
 * circulating. `faq.test.jsx` pins the parity, so a question cannot be added to
 * one language and quietly forgotten in another.
 */

export default [
  {
    id: 'que-es',
    q: 'What is OIUEEI?',
    a: "An app for sharing things among people who know each other: a family, a school, a community centre, a group of neighbours. Whoever runs the group creates a collection, lists what there is and decides who gets invited; everyone else browses, asks and books. It is not an open marketplace and it is not a social network: who comes in is always one person's decision.",
  },
  {
    id: 'precio',
    q: 'What does it cost?',
    a: 'Nothing, while OIUEEI is in testing. Accounts created during the alpha and beta stay free even once a paid plan arrives for new accounts — it is written into term 3 of the conditions. There are no prices to announce yet; when there are, they will be said here and in the conditions before anywhere else.',
    link: { to: '/legal', label: 'Read the conditions' },
  },
  {
    id: 'probar',
    q: 'Do I have to register to try it?',
    a: 'There is no sign-up form: you type your email at the front door and a link to get in arrives. The account it creates is **real and permanent** — whatever you do inside is yours and nobody touches it — while the example collections you land in are a shared window display that gets reset every so often. Giving and selling are open from the first minute; to run a group collection, or to lend and rent, you have to ask for access, because there somebody is already waiting to get something back.',
    link: { to: '/popin', label: 'Come in and look around' },
  },
  {
    id: 'sin-contrasena',
    q: 'Why is there no password?',
    a: 'Because one more password is one more password to lose, to reuse, or to have leaked. Every time you sign in you ask for a link by email, and that link expires after **24 hours**. Use an address you can genuinely read: it is the only key to the account.',
  },
  {
    id: 'terminado',
    q: 'Is it finished?',
    a: 'No. OIUEEI is in **alpha**: nothing is finished and you will find rough edges. The legal notice says the same and so does the repository, and the day that changes it will change in all three at once.',
  },
  {
    id: 'idiomas',
    q: 'Is it available in Catalan?',
    a: 'Yes. The interface and the emails are in **Catalan, Spanish and English**, and each person picks their own regardless of what everyone else picked. On top of that, whoever runs a group can write the title, the description and the tags in several languages at once, and each member reads the one that is theirs.',
  },
  {
    id: 'invitar',
    q: 'How do I invite my group?',
    a: 'From the collection, in three ways you can mix:\n\n- By **email**, one person at a time.\n- With a **shareable link** you paste wherever you already talk, and can revoke whenever you like.\n- With a **QR code** of that same link, for when you are all in the same room.\n\nAnd if it suits you, members can suggest who to invite: the decision stays yours, one by one.',
  },
  {
    id: 'reservas',
    q: 'How do bookings work?',
    a: '**Loans and rentals** come with dates: you pick a stretch of the calendar and whoever runs the collection accepts or declines. **Gifts and sales** carry no dates; you ask, and that is that. An unanswered request expires on its own after 72 hours, and a group can set in advance the lengths, or the pickup and return days, that suit it.',
  },
  {
    id: 'sin-devolver',
    q: 'What if somebody does not bring something back?',
    a: "The app reminds both sides the day before and keeps every thing's journey, so it is always clear whose hands it is in. Past that there are no fines and no automatic blocks: that is for the group to sort out, not for the software. A **deposit** can be written down along with the condition for getting it back, but it is information and nothing more — OIUEEI takes no money, holds no money, and is not part of the deal.",
  },
  {
    id: 'quien-ve',
    q: 'Who can see my things?',
    a: 'It depends on the collection they are in. A **private** collection is seen only by whoever runs it and the people invited: anyone else meets a closed door. A **public** collection can be opened by anyone holding the link, with no account and no invitation. Whoever runs it chooses which is which, can change it whenever they like, and an archived collection goes back to being visible only to them.',
  },
  {
    id: 'mis-datos',
    q: 'Can I take my data with me, or delete my account?',
    a: 'Both, whenever you like and without explaining yourself. From your profile you download a file with everything of yours, and whoever runs a collection can also download that whole collection. Deleting the account is confirmed by email and is **immediate and irreversible**: your things and your photos go with it, so download whatever you want to keep first.',
    link: { to: '/me/data', label: 'Download my data' },
  },
  {
    id: 'privacidad',
    q: 'What do you do with my data?',
    a: 'Only what the app needs in order to work, and it is set out in full in the privacy notice: what is kept, for how long, who else processes it and how it is deleted. There are no ads, no third-party cookies and no profiles to sell to anybody. If something in there does not make sense when you read it, say so: the notice gets fixed, not the answer.',
    link: { to: '/legal', label: 'Read the privacy notice' },
  },
];
