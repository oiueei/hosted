// Texto legal completo del despliegue www.oiueei.com. El repositorio standalone
// lleva la versión genérica; aquí este fichero la sustituye. La identidad del
// titular se inyecta desde VITE_LEGAL_OPERATOR / _NIF / _ADDRESS en tiempo de
// compilación (sustitución estática de Vite — ver
// frontend/scripts/check-legal-env.mjs), así que ni el NIF ni la dirección
// quedan como código.
export default `
# Nuestro compromiso

OIUEEI funciona sin publicidad y sin analítica de terceros: nadie te rastrea mientras la usas. Tus datos no son el producto — no se venden ni se ceden a nadie, nunca. No hay píxeles de seguimiento en los correos ni enlaces envueltos en rastreadores. Este compromiso está escrito en las reglas de diseño del proyecto y es su punto de partida, no la letra pequeña.

# Aviso legal

En cumplimiento de la Ley 34/2002 (LSSI-CE), el titular de www.oiueei.com es:

**${import.meta.env.VITE_LEGAL_OPERATOR}** — NIF ${import.meta.env.VITE_LEGAL_NIF} — ${import.meta.env.VITE_LEGAL_ADDRESS} — contacto: legal@oiueei.com.

OIUEEI es un proyecto personal: no hay ninguna sociedad detrás. Soy su creador, mantenedor y responsable.

# Política de privacidad

**Responsable del tratamiento:** el titular indicado en el Aviso legal.

**Qué datos trato, para qué y con qué base:**

- **Email y nombre** — tu cuenta y los enlaces mágicos de acceso (sin contraseñas), y los avisos propios del servicio. Base: ejecución del servicio (art. 6.1.b RGPD).
- **Perfil opcional** (bio, foto, idioma) — lo que tú decides mostrar. Base: ejecución del servicio.
- **Demografía opcional** (generación de nacimiento y código postal) — solo la ve quien administra tus comunidades, y en agregado; nunca es pública. Base: tu consentimiento (art. 6.1.a); la retiras dejando los campos en blanco.
- **El contenido que publicas** (colecciones, cosas y sus fotos, preguntas y respuestas, reservas) — el servicio mismo. Base: ejecución del servicio.
- **Registros técnicos** (dirección IP en registros de seguridad y límites de uso) — proteger el servicio del abuso. Base: interés legítimo (art. 6.1.f).
- **Métricas propias seudonimizadas** — recuentos agregados para operar el servicio; nunca salen de nuestra base de datos ni se comparten. Base: interés legítimo.
- **Correos:** los esenciales (acceso, invitaciones) se envían siempre; los de actividad los puedes desactivar; los de noticias solo se envían si tú los activas (art. 6.1.a).

**Quién trata datos por encargo:** Heroku/Salesforce (alojamiento, servidores en Irlanda; empresa estadounidense), Hetzner Online GmbH (imágenes y documentos, Alemania), Mailgun/Sinch (envío de correo, región europea), Sentry/Functional Software (monitorización de errores, datos alojados en la región europea, Alemania — los eventos se limpian de datos personales antes de enviarse) y Tally (el formulario de sugerencias, Bélgica — solo recibe algo si escribes en él). Las transferencias a EE. UU. se amparan en el EU-US Data Privacy Framework y/o cláusulas contractuales tipo.

**Lo que no hay:** publicidad, analítica de terceros, venta o cesión de datos, decisiones automatizadas ni perfilado. **Cookies y almacenamiento local:** solo lo técnico. Las cookies son de sesión y seguridad; en tu navegador se guardan además tu código de usuario, tus preferencias de idioma y de aspecto, y si ya has visto la bienvenida. Nada de eso necesita consentimiento, y por eso no hay banner.

**Cuánto tiempo:** mientras uses OIUEEI, y con un plazo por cada tipo de dato — nada se guarda para siempre. Si nadie inicia sesión en tu cuenta durante **24 meses** te aviso por correo, y si no vuelves en los **30 días** siguientes se borra (volver una sola vez pone el contador a cero); la excepción es una cuenta que es dueña de un grupo en uso, que se marca para que lo decida una persona en vez de borrarse sola. Las notificaciones de la app y las denuncias se guardan **12 meses**, el registro de actividad diaria **26**, y la analítica propia deja de estar ligada a una persona a los **14 meses** — se borra quién, se queda el hecho en agregado. Puedes **borrar tu cuenta tú mismo** (Editar perfil → Borrar cuenta, con confirmación por correo): es inmediato e irreversible — tu cuenta, tus colecciones, tus cosas y sus fotos y tus solicitudes se eliminan. Las preguntas que hiciste en cosas de otras personas y el historial de manos se conservan sin tu nombre («Antiguo miembro»). Las copias de seguridad se hacen a diario y rotan solas: las de más de una semana desaparecen.

**Tus derechos:** acceso, rectificación, supresión y portabilidad los ejerces directamente desde tu perfil: puedes descargar todos tus datos en un fichero cuando quieras y, si gestionas un grupo, también el grupo entero —ese segundo fichero lleva datos de otras personas, así que guárdalo bien—. Para oposición o limitación escríbeme a legal@oiueei.com. También puedes reclamar ante la Agencia Española de Protección de Datos (www.aepd.es).

**Si has llegado por una invitación:** tu correo nos lo dio quien te invitó, y solo se usa para enviarte esa invitación. Si no la aceptas y nadie vuelve a invitarte, esa cuenta pendiente se borra sola a los 60 días.

**Menores:** si tienes menos de 14 años, necesitas la autorización de tus tutores para usar OIUEEI.

**¿Buscas una respuesta rápida?** Las [preguntas frecuentes](/faq) cuentan lo mismo en lenguaje llano. Esta página es la versión completa, y es la que vale.

# Términos y condiciones

1. **Qué es.** OIUEEI es una plataforma para compartir cosas entre personas que se conocen. Está en fase **alfa**: nada está terminado y encontrarás bordes sin pulir.
2. **Tu cuenta.** Se accede con enlaces mágicos por correo; usa un email que puedas leer. Puedes borrar tu cuenta cuando quieras, desde tu perfil.
3. **Precio.** Durante la fase de pruebas (alfa y beta) el servicio es **gratuito**, y las cuentas creadas en esta etapa lo seguirán siendo. Más adelante está previsto un plan de pago para las cuentas nuevas; los precios se anunciarán aquí y en estos términos, con antelación, antes que en ningún otro sitio.
4. **Continuidad.** Las herramientas para exportar tus datos ya existen: desde tu perfil, cuando quieras, los tuyos en un fichero y —si gestionas un grupo— el grupo entero (sus cosas, sus miembros, el historial). Si algún día OIUEEI cerrara, avisaré con un **mínimo de 90 días**, tiempo de sobra para llevártelo a otra plataforma o auto-hospedar la aplicación desde GitHub (la licencia lo permite).
5. **Tu contenido.** Es tuyo y respondes de él. No publiques nada ilegal, dañino o que no te pertenezca. Hay un botón para denunciar contenido y puedo retirar lo que incumpla estas normas.
6. **Entre personas.** Los intercambios (regalos, ventas, préstamos, alquileres) son acuerdos entre usuarios: OIUEEI no es parte de ellos, no procesa pagos y no garantiza las transacciones. Una **fianza** anotada en una ficha es información que acuerdan las dos personas entre sí: OIUEEI no la cobra, no la retiene, no la mueve y no garantiza su devolución.
7. **Garantías.** El servicio se presta «tal cual», sin garantías, en la medida en que la ley lo permita. Nada de esto limita los derechos que la ley te reconozca como consumidor.
8. **Cambios.** Si estos términos cambian, avisaré con antelación razonable.
9. **Ley y fuero.** Ley española; para cualquier conflicto, los juzgados de Barcelona, salvo que como consumidor te corresponda el fuero de tu domicilio.

# El código

OIUEEI es software de código abierto bajo la licencia **EUPL-1.2**, un copyleft fuerte: puedes leerlo, modificarlo y auto-hospedarlo en producción, también como servicio. Lo que la licencia pide a cambio es reciprocidad — si ofreces un OIUEEI modificado como servicio en red, debes poner su código fuente a disposición de tus usuarios bajo la misma licencia; un despliegue sin modificar no debe nada más allá de conservar los avisos. El proyecto vive en GitHub (github.com/oiueei/standalone).

---

*Última actualización: 4 de septiembre de 2026.*
`;
