// Text legal complet del desplegament www.oiueei.com. El repositori standalone
// porta la versió genèrica; aquí aquest fitxer la substitueix. La identitat del
// titular s'injecta des de VITE_LEGAL_OPERATOR / _NIF / _ADDRESS en temps de
// compilació (substitució estàtica de Vite — vegeu
// frontend/scripts/check-legal-env.mjs), de manera que ni el NIF ni l'adreça
// queden com a codi.
export default `
# El nostre compromís

OIUEEI funciona sense publicitat i sense analítica de tercers: ningú no et rastreja mentre la fas servir. Les teves dades no són el producte — no es venen ni se cedeixen a ningú, mai. No hi ha píxels de seguiment als correus ni enllaços embolcallats amb rastrejadors. Aquest compromís està escrit a les regles de disseny del projecte i és el seu punt de partida, no la lletra petita.

# Avís legal

En compliment de la Llei 34/2002 (LSSI-CE), el titular de www.oiueei.com és:

**${import.meta.env.VITE_LEGAL_OPERATOR}** — NIF ${import.meta.env.VITE_LEGAL_NIF} — ${import.meta.env.VITE_LEGAL_ADDRESS} — contacte: legal@oiueei.com.

OIUEEI és un projecte personal: no hi ha cap societat al darrere. En soc el creador, mantenidor i responsable.

# Política de privadesa

**Responsable del tractament:** el titular indicat a l'Avís legal.

**Quines dades tracto, per a què i amb quina base:**

- **Email i nom** — el teu compte i els enllaços màgics d'accés (sense contrasenyes), i els avisos propis del servei. Base: execució del servei (art. 6.1.b RGPD).
- **Perfil opcional** (bio, foto, idioma) — el que tu decideixes mostrar. Base: execució del servei.
- **Demografia opcional** (generació de naixement i codi postal) — només la veu qui administra les teves comunitats, i en agregat; mai no és pública. Base: el teu consentiment (art. 6.1.a); el retires deixant els camps en blanc.
- **El contingut que publiques** (col·leccions, coses i les seves fotos, preguntes i respostes, reserves) — el servei mateix. Base: execució del servei.
- **Registres tècnics** (adreça IP en registres de seguretat i límits d'ús) — protegir el servei de l'abús. Base: interès legítim (art. 6.1.f).
- **Mètriques pròpies pseudonimitzades** — recomptes agregats per operar el servei; mai no surten de la nostra base de dades ni es comparteixen. Base: interès legítim.
- **Correus:** els essencials (accés, invitacions) s'envien sempre; els d'activitat els pots desactivar; els de notícies només s'envien si tu els actives (art. 6.1.a).

**Qui tracta dades per encàrrec:** Heroku/Salesforce (allotjament, servidors a Irlanda; empresa estatunidenca), Hetzner Online GmbH (imatges i documents, Alemanya), Mailgun/Sinch (enviament de correu, regió europea), Sentry/Functional Software (monitoratge d'errors, dades allotjades a la regió europea, Alemanya — els esdeveniments es netegen de dades personals abans d'enviar-se) i Tally (el formulari de suggeriments, Bèlgica — només rep res si hi escrius). Les transferències als EUA s'emparen en l'EU-US Data Privacy Framework i/o clàusules contractuals tipus.

**El que no hi ha:** publicitat, analítica de tercers, venda o cessió de dades, decisions automatitzades ni perfilat. **Galetes i emmagatzematge local:** només el tècnic. Les galetes són de sessió i seguretat; al teu navegador s'hi guarden a més el teu codi d'usuari, les teves preferències d'idioma i d'aspecte, i si ja has vist la benvinguda. Res d'això no necessita consentiment, i per això no hi ha bàner.

**Quant de temps:** mentre facis servir OIUEEI, i amb un termini per cada tipus de dada — res no es guarda per sempre. Si ningú no inicia sessió al teu compte durant **24 mesos** t'aviso per correu, i si no tornes en els **30 dies** següents s'esborra (tornar una sola vegada posa el comptador a zero); l'excepció és un compte que és propietari d'un grup en ús, que es marca perquè ho decideixi una persona en lloc d'esborrar-se sol. Un compte creat per una invitació que ningú no va arribar a acceptar s'esborra sol als **60 dies**. Les notificacions de l'app i les denúncies es guarden **12 mesos**, el registre d'activitat diària **26**, i l'analítica pròpia deixa d'estar lligada a una persona als **14 mesos** — s'esborra qui, es queda el fet en agregat. Pots **esborrar el teu compte tu mateix** (Editar perfil → Esborrar el compte, amb confirmació per correu): és immediat i irreversible — el teu compte, les teves col·leccions, les teves coses amb les seves fotos i les teves sol·licituds s'eliminen. Les preguntes que vas fer en coses d'altres persones i l'historial de mans es conserven sense el teu nom («Antic membre»). Les còpies de seguretat es fan cada dia i roten soles: les de més d'una setmana desapareixen.

**Els teus drets:** accés, rectificació, supressió i portabilitat els exerceixes directament des del teu perfil: pots descarregar totes les teves dades en un fitxer quan vulguis i, si gestiones un grup, també el grup sencer —aquest segon fitxer porta dades d'altres persones, així que guarda'l bé—. Per a oposició o limitació escriu-me a legal@oiueei.com. També pots reclamar davant l'Agència Espanyola de Protecció de Dades (www.aepd.es).

**Si hi has arribat per una invitació:** el teu correu ens el va donar qui et va convidar, i només es fa servir per enviar-te aquesta invitació. Si no l'acceptes i ningú no torna a convidar-te, aquest compte pendent s'esborra sol als 60 dies.

**Menors:** si tens menys de 14 anys, necessites l'autorització dels teus tutors per fer servir OIUEEI.

**Busques una resposta ràpida?** Les [preguntes freqüents](/faq) expliquen el mateix en llenguatge planer. Aquesta pàgina és la versió completa, i és la que val.

# Termes i condicions

1. **Què és.** OIUEEI és una plataforma per compartir coses entre persones que es coneixen. És en fase **alfa**: res no està acabat i hi trobaràs vores per polir.
2. **El teu compte.** S'hi accedeix amb enllaços màgics per correu; fes servir un email que puguis llegir. Pots esborrar el teu compte quan vulguis, des del teu perfil.
3. **Preu.** Durant la fase de proves (alfa i beta) el servei és **gratuït**, i els comptes creats en aquesta etapa ho continuaran sent. Més endavant està previst un pla de pagament per als comptes nous; els preus s'anunciaran aquí, i en aquests termes, amb antelació, abans que enlloc més.
4. **Continuïtat.** Les eines per exportar les teves dades ja existeixen: des del teu perfil, quan vulguis, les teves en un fitxer i —si gestiones un grup— el grup sencer (les seves coses, els seus membres, l'historial). Si algun dia OIUEEI tanqués, avisaré amb un **mínim de 90 dies**, temps de sobra per emportar-t'ho a una altra plataforma o auto-hospedar l'aplicació des de GitHub (la llicència ho permet).
5. **El teu contingut.** És teu i n'ets responsable. No publiquis res il·legal, nociu o que no et pertanyi. Hi ha un botó per denunciar contingut i puc retirar el que incompleixi aquestes normes.
6. **Entre persones.** Els intercanvis (regals, vendes, préstecs, lloguers) són acords entre usuaris: OIUEEI no n'és part, no processa pagaments i no garanteix les transaccions. Una **fiança** anotada en una fitxa és informació que acorden les dues persones entre elles: OIUEEI no la cobra, no la reté, no la mou i no en garanteix la devolució.
7. **Garanties.** El servei es presta «tal com és», sense garanties, en la mesura que la llei ho permeti. Res d'això no limita els drets que la llei et reconegui com a consumidor.
8. **Canvis.** Si aquests termes canvien, avisaré amb antelació raonable.
9. **Llei i fur.** Llei espanyola; per a qualsevol conflicte, els jutjats de Barcelona, llevat que com a consumidor et correspongui el fur del teu domicili.

# El codi

OIUEEI és programari de codi obert sota la llicència **EUPL-1.2**, un copyleft fort: pots llegir-lo, modificar-lo i auto-hospedar-lo en producció, també com a servei. El que la llicència demana a canvi és reciprocitat — si ofereixes un OIUEEI modificat com a servei en xarxa, has de posar el seu codi font a disposició dels teus usuaris sota la mateixa llicència; un desplegament sense modificar no deu res més enllà de conservar els avisos. El projecte viu a GitHub (github.com/oiueei/standalone).

---

*Darrera actualització: 4 de setembre de 2026.*
`;
