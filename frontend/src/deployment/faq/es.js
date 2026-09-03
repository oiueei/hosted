/**
 * The help page's questions and answers, in Spanish.
 *
 * This deployment's content, not the product's: what it costs, who runs it,
 * what state it is in and what the door at /popin does are all one operator's
 * answers, which is why the whole page lives in `src/deployment/` rather than
 * in `src/pages/`. A self-hoster copying these sentences would be publishing
 * claims that are not theirs.
 *
 * Shape — an array, not one Markdown blob, so that each question gets a stable
 * anchor (`/faq#precio`) worth pasting into a chat, and so the three languages
 * can be checked against each other by `id`:
 *
 *   id    stable and shared across languages, in Spanish like the rest of the
 *         repo's codes. Changing one breaks links that are already circulating.
 *   q     the question. The page renders it as its own `<h2 id={id}>`.
 *   a     the answer in Markdown, rendered by `MarkdownText`.
 *   link  optional destination inside the app. It is a separate field rather
 *         than a Markdown link because `MarkdownText` opens every anchor with
 *         target="_blank" — right for an outside link, wrong for /legal — and
 *         that component is shared with upstream, so this deployment does not
 *         get to change it. The page renders this one as a router link.
 *
 * Rules this file lives by: every answer is checkable against the product as it
 * is today, two to four sentences, and understandable pulled out of context. No
 * placeholder ever ships — a fact we do not have yet is a question we ask, not
 * a sentence we invent.
 */

export default [
  {
    id: 'que-es',
    q: '¿Qué es OIUEEI?',
    a: 'Una aplicación para compartir cosas entre personas que se conocen: una familia, una escuela, un ateneo, un grupo de vecinas. Quien gestiona el grupo crea una colección, apunta lo que hay y decide a quién invita; el resto mira, pide y reserva. No es un mercado abierto ni una red social: quién entra lo decide siempre una persona concreta.',
  },
  {
    id: 'precio',
    q: '¿Cuánto cuesta?',
    a: 'Nada, mientras OIUEEI está en pruebas. Las cuentas creadas durante la alfa y la beta seguirán siendo gratuitas aunque más adelante haya un plan de pago para las cuentas nuevas — está escrito en el término 3 de las condiciones. Todavía no hay precios que anunciar; cuando los haya se dirán aquí y en las condiciones antes que en ningún otro sitio.',
    link: { to: '/legal', label: 'Leer las condiciones' },
  },
  {
    id: 'probar',
    q: '¿Tengo que registrarme para probarlo?',
    a: 'No hay formulario de registro: escribes tu correo en la puerta de entrada y te llega un enlace para entrar. La cuenta que se crea es **real y permanente** —lo que hagas dentro es tuyo y no lo toca nadie—, mientras que las colecciones de ejemplo en las que aterrizas son un escaparate compartido que se reinicia cada cierto tiempo. Regalar y vender están abiertos desde el primer minuto; para montar una colección de grupo o para prestar y alquilar hay que pedir acceso, porque ahí ya hay alguien esperando algo de vuelta.',
    link: { to: '/popin', label: 'Entrar y mirar' },
  },
  {
    id: 'sin-contrasena',
    q: '¿Por qué no hay contraseña?',
    a: 'Porque una contraseña más es una contraseña más que perder, repetir o que se filtre. Cada vez que entras pides un enlace a tu correo, y ese enlace caduca a las **24 horas**. Usa una dirección que puedas leer de verdad: es la única llave de la cuenta.',
  },
  {
    id: 'terminado',
    q: '¿Está terminado?',
    a: 'No. OIUEEI está en **fase alfa**: nada está terminado y encontrarás bordes sin pulir. Lo dice igual el aviso legal y lo dice el repositorio, y el día que eso cambie cambiará en los tres sitios a la vez.',
  },
  {
    id: 'idiomas',
    q: '¿Está en catalán?',
    a: 'Sí. La interfaz y los correos están en **catalán, castellano e inglés**, y cada persona elige el suyo sin depender de lo que hayan elegido los demás. Además, quien gestiona un grupo puede escribir el título, la descripción y las etiquetas en varios idiomas a la vez, y cada miembro lee la versión que le toca.',
  },
  {
    id: 'invitar',
    q: '¿Cómo invito a mi grupo?',
    a: 'Desde la colección, de tres maneras que puedes mezclar:\n\n- Por **correo**, una persona cada vez.\n- Con un **enlace para compartir**, que pegas donde ya habléis y puedes revocar cuando quieras.\n- Con un **código QR** de ese mismo enlace, para cuando estáis en la misma sala.\n\nY si te viene bien, los miembros pueden proponerte a quién invitar: la decisión sigue siendo tuya, una por una.',
  },
  {
    id: 'reservas',
    q: '¿Cómo funcionan las reservas?',
    a: 'Los **préstamos y alquileres** van con fechas: se elige un tramo en el calendario y quien gestiona la colección acepta o rechaza. Los **regalos y las ventas** no llevan fechas; se piden y ya está. Una solicitud sin responder caduca sola a las 72 horas, y un grupo puede fijar de antemano las duraciones o los días de recogida y devolución que le encajen.',
  },
  {
    id: 'sin-devolver',
    q: '¿Qué pasa si alguien no devuelve algo?',
    a: 'La aplicación avisa el día antes a las dos partes y guarda el recorrido de cada cosa, así que siempre se sabe en qué manos está. A partir de ahí no hay multas ni bloqueos automáticos: eso lo arregla el grupo, no el software. Se puede anotar una **fianza** y la condición para recuperarla, pero es información y nada más — OIUEEI no cobra, no retiene dinero y no es parte del trato.',
  },
  {
    id: 'quien-ve',
    q: '¿Quién ve mis cosas?',
    a: 'Depende de la colección donde estén. Una colección **privada** solo la ven quien la gestiona y las personas invitadas: cualquier otro se lleva un portazo. Una colección **pública** puede abrirla cualquiera que tenga el enlace, sin cuenta y sin invitación. Quien gestiona elige cuál es cada una, puede cambiarlo cuando quiera, y una colección archivada vuelve a verla solo esa persona.',
  },
  {
    id: 'mis-datos',
    q: '¿Puedo llevarme mis datos o borrar la cuenta?',
    a: 'Las dos cosas, cuando quieras y sin dar explicaciones. Desde tu perfil descargas un archivo con todo lo tuyo, y quien gestiona una colección puede descargar además la colección entera. Borrar la cuenta se confirma por correo y es **inmediato e irreversible**: se van también tus cosas y tus fotos, así que descarga antes lo que quieras conservar.',
    link: { to: '/me/data', label: 'Descargar mis datos' },
  },
  {
    id: 'privacidad',
    q: '¿Qué hacéis con mis datos?',
    a: 'Lo justo para que la aplicación funcione, y está contado entero en el aviso de privacidad: qué se guarda, cuánto tiempo, quién más lo trata y cómo se borra. No hay publicidad, ni cookies de terceros, ni perfiles para vender a nadie. Si al leerlo hay algo que no se entiende, dilo: se arregla el aviso, no la respuesta.',
    link: { to: '/legal', label: 'Leer el aviso de privacidad' },
  },
];
