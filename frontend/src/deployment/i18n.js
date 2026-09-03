/**
 * The copy for this deployment's own pages, merged into the `translation`
 * namespace at startup (see `i18n/index.js`).
 *
 * It lives here rather than in `i18n/locales/*.json` because those three files
 * are edited constantly upstream, and every string this deployment adds to them
 * would be a merge conflict on every release.
 */

export const deploymentI18n = {
  en: {
    popin: {
      title: 'Come meet us!',
      description:
        "Enter your email and we'll send you a magic link. One click and you're in — no password, no faff.",
      emailLabel: 'Email',
      emailPlaceholder: 'you@email.com',
      join: 'Pop in',
      joining: 'Sending…',
      magicLinkSent: 'Magic link sent! Check your inbox and click the link to join.',
      closeThisTab: 'You can close this tab now — the link is on its way to your inbox.',
      errorSendingLink: 'Error sending link.',
      alreadyHaveAccount: 'Already have an account? Sign in →',
    },
    welcome: {
      greeting: 'Hello, {{name}}',
      pageTitle: 'Welcome to OIUEEI!',
      description:
        'OIUEEI is an open source platform for sharing within trusted communities. Create collections for gifts, sales, rentals and loans — then invite friends to browse, reserve and interact. Everything stays between people who know each other.',
      createShare:
        "OIUEEI revolves around your own collections. Create one for anything you'd like to share — gifts, sales, rentals or loans — and invite your circles: family, friends, neighbours, your street. Only the people you invite can see it and join in.",
      commitmentTitle: 'Our commitment',
      commitmentBody1:
        'OIUEEI runs without ads and without third-party analytics: nobody tracks you while you use it. Your data is not the product — it is never sold or shared with anyone.',
      commitmentBody2:
        "The code is public and you can read all of it; this commitment is <1>written into our design rules</1>. It's not the fine print: it's the starting point.",
      createCollection: 'Create collection',
      editProfile: 'Edit profile',
      whoUsesTitle: 'Who uses OIUEEI?',
      exampleIntro:
        "To show you how it works, we've shared a few example collections with you. Meet the people below and step into their collections — read on and you'll get the idea.",
      exampleIntroEmpty: 'These stories show the kinds of things people share on OIUEEI.',
      personaLalaTitle: 'Lala — The Declutterer.',
      personaLalaBody:
        "Off on sabbatical and clearing out the flat with zero fuss — a tenner each, you come collect, everything gone by the 25th. Whatever's left goes straight to the local orphanage.",
      personaLeleTitle: 'Lele — The Neighbour.',
      personaLeleBody:
        'She lives in a housing cooperative where almost nothing gets done alone. Every Sunday she sets up a swap-meet-party-lunch in the courtyard: everyone brings down what they no longer use, someone puts music on, and there is always more food than people. Bring a dish, leave with a recipe.',
      personaLiliTitle: 'Lili — The Lender.',
      personaLiliBody:
        "Her neighbourhood lending library has the lot: drills and steam cleaners, but also kitchen kit, garden gear, sports and baby bits — because nobody should buy what they'll only use once in a blue moon. Borrow it, use it, return it clean. That's the deal.",
      personaLoloTitle: 'Lolo — The Green Thumb.',
      personaLoloBody:
        'A plant parent with far too many green babies, giving away succulent cuttings from a beautifully curated collection — echeverias, jades, sedums, the lot. Adopt a pup; the only rule is that you have to name it.',
      personaLuluTitle: 'Lulu — The Connector.',
      personaLuluBody:
        'Nobody quite knows how they hear about everything first, but they do. Now they keep the neighbourhood shared workshop: the tools belong to everyone, anyone can add theirs and anyone can lend them out. Every neighbourhood needs one.',
      personaLeleLink1: 'The Sunday swap-meet',
      personaLiliLink1: "Lili's Lending Library",
      personaLuluLink1: "Lulu's shared workshop",
      personaLoloLink1: "Lolo's Leafy Lounge",
      personaLalaLink2: "Lala's sabbatical sale",
      enterCta: 'Enter and see how it works',
      legalLink: 'Legal notice & privacy →',
      faqLink: 'Frequently asked questions →',
    },
    login: {
      operator:
        'Everything that touches your data runs on European servers. The person who maintains OIUEEI lives in Barcelona and is named, in full, in the legal notice.',
    },
    faqPage: {
      pageTitle: 'Frequently asked questions',
    },
    titles: {
      popin: 'Pop in — OIUEEI',
      welcome: 'Welcome — OIUEEI',
      faqPage: 'Frequently asked questions — OIUEEI',
    },
  },
  es: {
    popin: {
      title: '¡Ven a conocernos!',
      description:
        'Introduce tu email y te enviaremos un enlace mágico. Un clic y ya estás dentro — sin contraseñas, sin líos.',
      emailLabel: 'Email',
      emailPlaceholder: 'tu@email.com',
      join: 'Pásate',
      joining: 'Enviando…',
      magicLinkSent: '¡Enlace enviado! Revisa tu bandeja de entrada y pulsa el enlace para unirte.',
      closeThisTab:
        'Ya puedes cerrar esta pestaña — el enlace está de camino a tu bandeja de entrada.',
      alreadyHaveAccount: '¿Ya tienes cuenta? Inicia sesión →',
      errorSendingLink: 'Error al enviar el enlace.',
    },
    welcome: {
      greeting: 'Hola, {{name}}',
      pageTitle: '¡Bienvenido a OIUEEI!',
      description:
        'OIUEEI es una plataforma de código abierto para compartir dentro de comunidades de confianza. Crea colecciones para regalos, ventas, alquileres y préstamos — luego invita a amigos a explorar, reservar e interactuar. Todo queda entre personas que se conocen.',
      createShare:
        'OIUEEI gira en torno a tus propias colecciones. Crea una para lo que quieras compartir —regalos, ventas, alquileres o préstamos— e invita a tus círculos: familia, amigos, vecinos, tu calle. Solo quienes invites pueden verla y participar.',
      commitmentTitle: 'Nuestro compromiso',
      commitmentBody1:
        'OIUEEI funciona sin anuncios y sin analíticas de terceros: nadie te rastrea mientras la usas. Tus datos no son el producto — no se venden ni se comparten con nadie.',
      commitmentBody2:
        'El código es público y puedes leerlo todo; este compromiso está <1>escrito en nuestras reglas de diseño</1>. No es la letra pequeña: es el punto de partida.',
      createCollection: 'Crear colección',
      editProfile: 'Editar perfil',
      whoUsesTitle: '¿Quién usa OIUEEI?',
      exampleIntro:
        'Para enseñarte cómo funciona, te hemos compartido algunas colecciones de ejemplo. Conoce a las personas de abajo y entra en sus colecciones — sigue leyendo y lo entenderás.',
      exampleIntroEmpty:
        'Estas historias muestran el tipo de cosas que las personas comparten en OIUEEI.',
      personaLalaTitle: 'Lala — La Desapegada.',
      personaLalaBody:
        'De sabático y vaciando el piso sin complicaciones — diez euros cada cosa, tú lo recoges, todo cerrado antes del 25. Lo que sobre, directo al orfanato del barrio.',
      personaLeleTitle: 'Lele — La Vecina.',
      personaLeleBody:
        'Vive en una cooperativa de viviendas donde casi nada se hace en solitario. Cada domingo monta en el patio un mercadillo-fiesta-comida: cada cual baja lo que ya no usa, alguien pone música y siempre acaba habiendo más comida que gente. Trae plato, te vas con receta.',
      personaLiliTitle: 'Lili — La Prestadora.',
      personaLiliBody:
        'Su biblioteca de préstamos del barrio tiene de todo: taladros y vaporetas, pero también cosas de cocina, jardín, deporte y crianza — porque nadie necesita comprar lo que usa de uvas a peras. Pídelo prestado, úsalo y devuélvelo limpio. Ese es el trato.',
      personaLoloTitle: 'Lolo — El Jardinero.',
      personaLoloBody:
        'Mamá planta con demasiadas crías verdes, regala esquejes de suculentas desde una preciosa colección — echeverias, jades, sedums, de todo. Adopta una cría; la única regla es que tienes que ponerle nombre.',
      personaLuluTitle: 'Lulu — El Conector.',
      personaLuluBody:
        'Nadie sabe muy bien cómo se entera de todo antes que nadie, pero se entera. Ahora guarda el taller compartido del barrio: las herramientas son de todas, cualquiera sube las suyas y cualquiera las presta. En todo barrio hace falta alguien así.',
      personaLeleLink1: 'El mercadillo de los domingos',
      personaLiliLink1: 'La biblioteca de préstamos de Lili',
      personaLuluLink1: 'El taller compartido de Lulu',
      personaLoloLink1: 'El salón verde de Lolo',
      personaLalaLink2: 'La venta del sabático de Lala',
      enterCta: 'Entrar y ver cómo funciona',
      legalLink: 'Aviso legal y privacidad →',
      faqLink: 'Preguntas frecuentes →',
    },
    login: {
      operator:
        'Todo lo que toca tus datos funciona en servidores europeos. Quien mantiene OIUEEI vive en Barcelona y da la cara con nombre y apellidos en el aviso legal.',
    },
    faqPage: {
      pageTitle: 'Preguntas frecuentes',
    },
    titles: {
      popin: 'Pásate — OIUEEI',
      welcome: 'Bienvenido — OIUEEI',
      faqPage: 'Preguntas frecuentes — OIUEEI',
    },
  },
  ca: {
    popin: {
      title: 'Vine a conèixer-nos!',
      description:
        "Introdueix el teu correu i t'enviarem un enllaç màgic. Un clic i ja hi ets — sense contrasenya, sense complicacions.",
      emailLabel: 'Correu',
      emailPlaceholder: 'tu@correu.com',
      join: 'Passa',
      joining: 'Enviant…',
      magicLinkSent: "Enllaç enviat! Revisa la safata d'entrada i fes clic a l'enllaç per unir-te.",
      closeThisTab:
        "Ja pots tancar aquesta pestanya — l'enllaç ja és de camí a la teva safata d'entrada.",
      alreadyHaveAccount: 'Ja tens un compte? Inicia sessió →',
      errorSendingLink: "Error en enviar l'enllaç.",
    },
    welcome: {
      greeting: 'Hola, {{name}}',
      pageTitle: 'Benvingut a OIUEEI!',
      description:
        'OIUEEI és una plataforma de codi obert per compartir dins de comunitats de confiança. Crea col·leccions per a regals, vendes, lloguers i préstecs — després convida amics a explorar, reservar i interactuar. Tot queda entre persones que es coneixen.',
      createShare:
        "OIUEEI gira al voltant de les teves pròpies col·leccions. Crea'n una per a allò que vulguis compartir —regals, vendes, lloguers o préstecs— i convida els teus cercles: família, amics, veïns, el teu carrer. Només qui convidis pot veure-la i participar-hi.",
      commitmentTitle: 'El nostre compromís',
      commitmentBody1:
        'OIUEEI funciona sense anuncis i sense analítiques de tercers: ningú no et rastreja mentre la fas servir. Les teves dades no són el producte — no es venen ni es comparteixen amb ningú.',
      commitmentBody2:
        'El codi és públic i pots llegir-lo tot; aquest compromís està <1>escrit a les nostres regles de disseny</1>. No és la lletra petita: és el punt de partida.',
      createCollection: 'Crear col·lecció',
      editProfile: 'Editar perfil',
      whoUsesTitle: 'Qui fa servir OIUEEI?',
      exampleIntro:
        "Per ensenyar-te com funciona, t'hem compartit algunes col·leccions d'exemple. Coneix les persones de sota i entra a les seves col·leccions — continua llegint i ho entendràs.",
      exampleIntroEmpty:
        'Aquestes històries mostren els tipus de coses que la gent comparteix a OIUEEI.',
      personaLalaTitle: 'Lala — La Despresa.',
      personaLalaBody:
        "De sabàtic i buidant el pis sense complicacions — deu euros cada cosa, tu ho recolls, tot tancat abans del 25. El que sobri, directe a l'orfenat del barri.",
      personaLeleTitle: 'Lele — La Veïna.',
      personaLeleBody:
        "Viu en una cooperativa d'habitatge on gairebé res no es fa en solitari. Cada diumenge munta al pati un mercadet-festa-dinar: cadascú baixa el que ja no fa servir, algú posa música i sempre acaba havent-hi més menjar que gent. Porta plat, te'n vas amb recepta.",
      personaLiliTitle: 'Lili — La Prestadora.',
      personaLiliBody:
        'La seva biblioteca de préstecs del barri ho té tot: trepants i vaporetes, però també coses de cuina, jardí, esport i criança — perquè ningú no hauria de comprar el que fa servir de Pasqua a Rams. Demana-ho en préstec, fes-ho servir i torna-ho net. Aquest és el tracte.',
      personaLoloTitle: 'Lolo — El Jardiner.',
      personaLoloBody:
        "Mare planta amb massa cries verdes, regala esqueixos de suculentes d'una preciosa col·lecció — echeverias, jades, sedums, de tot. Adopta una cria; l'única regla és que li has de posar nom.",
      personaLuluTitle: 'Lulu — El Connector.',
      personaLuluBody:
        "Ningú no sap gaire bé com s'assabenta de tot abans que ningú, però se n'assabenta. Ara guarda el taller compartit del barri: les eines són de tothom, qualsevol hi puja les seves i qualsevol les deixa. A tot barri en cal algú així.",
      personaLeleLink1: 'El mercadet dels diumenges',
      personaLiliLink1: 'La biblioteca de préstecs de la Lili',
      personaLuluLink1: 'El taller compartit de la Lulu',
      personaLoloLink1: "El saló verd d'en Lolo",
      personaLalaLink2: 'La venda del sabàtic de la Lala',
      enterCta: 'Entra i mira com funciona',
      legalLink: 'Avís legal i privadesa →',
      faqLink: 'Preguntes freqüents →',
    },
    login: {
      operator:
        "Tot allò que toca les teves dades funciona en servidors europeus. Qui manté OIUEEI viu a Barcelona i hi dona la cara amb nom i cognoms a l'avís legal.",
    },
    faqPage: {
      pageTitle: 'Preguntes freqüents',
    },
    titles: {
      popin: 'Passa — OIUEEI',
      welcome: 'Benvingut — OIUEEI',
      faqPage: 'Preguntes freqüents — OIUEEI',
    },
  },
};
