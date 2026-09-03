/**
 * The help page's questions and answers, in Catalan.
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
    q: 'Què és OIUEEI?',
    a: 'Una aplicació per compartir coses entre persones que es coneixen: una família, una escola, un ateneu, un grup de veïnes. Qui gestiona el grup crea una col·lecció, hi apunta el que hi ha i decideix a qui convida; la resta mira, demana i reserva. No és un mercat obert ni una xarxa social: qui hi entra ho decideix sempre una persona concreta.',
  },
  {
    id: 'precio',
    q: 'Quant costa?',
    a: "Res, mentre OIUEEI està en proves. Els comptes creats durant l'alfa i la beta continuaran sent gratuïts encara que més endavant hi hagi un pla de pagament per als comptes nous — està escrit al terme 3 de les condicions. Encara no hi ha preus per anunciar; quan n'hi hagi es diran aquí i a les condicions abans que enlloc més.",
    link: { to: '/legal', label: 'Llegir les condicions' },
  },
  {
    id: 'probar',
    q: "M'he de registrar per provar-ho?",
    a: "No hi ha formulari de registre: escrius el teu correu a la porta d'entrada i t'arriba un enllaç per entrar. El compte que es crea és **real i permanent** —el que facis a dins és teu i no ho toca ningú—, mentre que les col·leccions d'exemple on aterres són un aparador compartit que es reinicia cada cert temps. Regalar i vendre són oberts des del primer minut; per muntar una col·lecció de grup o per deixar i llogar cal demanar accés, perquè allà ja hi ha algú esperant que li tornin alguna cosa.",
    link: { to: '/popin', label: 'Entrar i mirar' },
  },
  {
    id: 'sin-contrasena',
    q: 'Per què no hi ha contrasenya?',
    a: "Perquè una contrasenya més és una contrasenya més per perdre, repetir o que et filtrin. Cada vegada que entres demanes un enllaç al teu correu, i aquest enllaç caduca al cap de **24 hores**. Fes servir una adreça que puguis llegir de debò: és l'única clau del compte.",
  },
  {
    id: 'terminado',
    q: 'Està acabat?',
    a: "No. OIUEEI és en **fase alfa**: res no està acabat i hi trobaràs vores per polir. Ho diu igual l'avís legal i ho diu el repositori, i el dia que això canviï canviarà als tres llocs alhora.",
  },
  {
    id: 'idiomas',
    q: 'És en català?',
    a: 'Sí. La interfície i els correus són en **català, castellà i anglès**, i cada persona tria el seu sense dependre del que hagin triat els altres. A més, qui gestiona un grup pot escriure el títol, la descripció i les etiquetes en diversos idiomes alhora, i cada membre llegeix la versió que li toca.',
  },
  {
    id: 'invitar',
    q: 'Com convido el meu grup?',
    a: "Des de la col·lecció, de tres maneres que pots barrejar:\n\n- Per **correu**, una persona cada vegada.\n- Amb un **enllaç per compartir**, que enganxes on ja parleu i pots revocar quan vulguis.\n- Amb un **codi QR** d'aquest mateix enllaç, per quan sou a la mateixa sala.\n\nI si et va bé, els membres et poden proposar a qui convidar: la decisió continua sent teva, una per una.",
  },
  {
    id: 'reservas',
    q: 'Com funcionen les reserves?',
    a: 'Els **préstecs i lloguers** van amb dates: es tria un tram al calendari i qui gestiona la col·lecció accepta o rebutja. Els **regals i les vendes** no porten dates; es demanen i ja està. Una sol·licitud sense resposta caduca sola al cap de 72 hores, i un grup pot fixar per endavant les durades o els dies de recollida i devolució que li encaixin.',
  },
  {
    id: 'sin-devolver',
    q: 'Què passa si algú no torna una cosa?',
    a: "L'aplicació avisa el dia abans les dues parts i guarda el recorregut de cada cosa, així que sempre se sap en quines mans és. A partir d'aquí no hi ha multes ni bloquejos automàtics: això ho arregla el grup, no el programari. Es pot anotar una **fiança** i la condició per recuperar-la, però és informació i res més — OIUEEI no cobra, no reté diners i no és part del tracte.",
  },
  {
    id: 'quien-ve',
    q: 'Qui veu les meves coses?',
    a: "Depèn de la col·lecció on siguin. Una col·lecció **privada** només la veuen qui la gestiona i les persones convidades: qualsevol altre es troba la porta tancada. Una col·lecció **pública** la pot obrir qualsevol que tingui l'enllaç, sense compte i sense invitació. Qui la gestiona tria què és cadascuna, ho pot canviar quan vulgui, i una col·lecció arxivada torna a veure-la només aquesta persona.",
  },
  {
    id: 'mis-datos',
    q: 'Puc endur-me les meves dades o esborrar el compte?',
    a: "Totes dues coses, quan vulguis i sense donar explicacions. Des del teu perfil et descarregues un arxiu amb tot el que és teu, i qui gestiona una col·lecció pot descarregar-se a més la col·lecció sencera. Esborrar el compte es confirma per correu i és **immediat i irreversible**: també se'n van les teves coses i les teves fotos, així que descarrega't abans el que vulguis conservar.",
    link: { to: '/me/data', label: 'Descarregar les meves dades' },
  },
  {
    id: 'privacidad',
    q: 'Què feu amb les meves dades?',
    a: "El just perquè l'aplicació funcioni, i és explicat sencer a l'avís de privacitat: què es guarda, quant de temps, qui més ho tracta i com s'esborra. No hi ha publicitat, ni galetes de tercers, ni perfils per vendre a ningú. Si en llegir-ho hi ha res que no s'entén, digues-ho: s'arregla l'avís, no la resposta.",
    link: { to: '/legal', label: "Llegir l'avís de privacitat" },
  },
];
