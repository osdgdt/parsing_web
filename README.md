# parsing_web — Lavoro a Brescia

Pagina statica che mostra offerte di lavoro (cameriera / commessa / barista / cassiera /
cucina / reception) a Brescia e dintorni (~10 km), aggiornata automaticamente una volta al
giorno da una routine cloud (Claude schedule/RemoteTrigger), più a comando tramite il tasto
"Aggiorna ora" sulla pagina stessa.

## Come funziona

- `index.html` — pagina statica (HTML/CSS/JS vanilla), legge `data.json` e mostra le
  offerte con filtri lato client (ruolo, tipo contratto, comune, fonte, "solo nuovi di
  oggi", "solo con stipendio") più una casella di ricerca testuale (titolo + azienda +
  descrizione). Contiene anche il tasto "Aggiorna ora" (vedi sotto). Non va mai modificata
  dalla routine giornaliera né dalla GitHub Action di verifica link.
- `data.json` — unica fonte di stato/storico. Schema:
  ```json
  {
    "lastUpdated": "ISO 8601",
    "listings": [
      {
        "id": "stringa univoca (URL normalizzato o hash azienda+titolo+luogo)",
        "role": "cameriera|commessa|barista|cassiera|cucina|reception",
        "title": "string",
        "company": "string",
        "location": "string (testo libero, solo per visualizzazione)",
        "comune": "brescia|rezzato|botticino|san-zeno-naviglio|castenedolo|bagnolo-mella|mazzano|concesio|bovezzo|collebeato|nuvolento|nuvolera",
        "url": "string",
        "source": "indeed|infojobs|subito|bakeca|adecco|randstad|gigroup|regione-lombardia|linkedin",
        "salary": "string o null",
        "contractType": "tempo-pieno|part-time|weekend-sera|indifferente",
        "datePosted": "ISO 8601 o null",
        "description": "string breve",
        "firstSeen": "ISO 8601 (data prima comparsa)",
        "lastSeen": "ISO 8601 (data ultima volta trovato nelle ricerche)",
        "linkVerifyFailCount": "intero, opzionale — gestito SOLO da scripts/verify_links.py, la routine non deve mai toccarlo se già presente"
      }
    ]
  }
  ```
- **Routine giornaliera** (Claude RemoteTrigger, trigger id `trig_01YSFVi49aHWQ2QrZyrVW1Ev`,
  cron `0 5 * * *` UTC ≈ 7:00 Europe/Rome): cerca su Indeed, InfoJobs, Subito.it, Bakeca,
  Adecco, Randstad, Gi Group, Borsa Lavoro Regione Lombardia (+ LinkedIn best-effort),
  aggiorna/aggiunge annunci in `data.json`, fa scadere quelli non più visti da oltre ~21
  giorni, poi fa commit + push. GitHub Pages ripubblica automaticamente in ~1 minuto.
  Gira nella sandbox cloud "CCR" di Claude, che **blocca l'accesso diretto** (WebFetch) a
  tutti i domini dei portali di lavoro — la routine usa quindi solo gli snippet di
  WebSearch, non apre mai le singole pagine annuncio.
- **Tasto "Aggiorna ora"** (in `index.html`): chiama un piccolo **Cloudflare Worker**
  pubblico (`https://web-parser.roberto-modonesi1.workers.dev`, account Cloudflare di
  Roberto) con un semplice `POST`, senza header o corpo. Il Worker (codice sorgente in
  `cloudflare-worker.js`, incollato manualmente nell'editor Cloudflare — non è collegato
  automaticamente a questo repo) usa un token GitHub salvato come **secret** nelle sue
  impostazioni (Settings → Variables and Secrets → `GITHUB_PAT`, mai nel codice né in
  questo repository) per aggiornare `trigger.json` sul branch dedicato `refresh-trigger`
  tramite la Contents API di GitHub. Un webhook trigger collegato alla routine
  (`RemoteTrigger action=create_webhook_trigger`, evento `push`, scope l'intero repository)
  fa scattare la stessa routine giornaliera ad ogni push su qualsiasi branch — non solo su
  `refresh-trigger` (un tentativo di limitarlo con `filter.ref` è stato accettato dalla API
  ma silenziosamente ignorato: verificato empiricamente che un push su `main` fa comunque
  scattare una nuova esecuzione).
  - **Perché non un token incorporato direttamente in `index.html`** (approccio tentato
    per primo): **GitHub revoca automaticamente qualsiasi suo Personal Access Token
    rilevato in un repository pubblico**, pochi secondi dopo il push, indipendentemente
    dal fatto che la protezione "push cannot contain secrets" venga superata manualmente.
    È una misura di sicurezza nativa di GitHub (parte del suo stesso "secret scanning
    partner program"), non aggirabile: qualunque token ci si mettesse morirebbe
    all'istante. Da qui la necessità del Worker come intermediario — il token vive solo
    lato server Cloudflare, mai in codice committato pubblicamente.
  - Protezioni anti-abuso: cooldown di 15 minuti lato pagina (solo UX, mostra un conto
    alla rovescia, non è una barriera reale dato che il Worker è un endpoint pubblico) +
    guardia lato routine (passo 0 del prompt: se `lastUpdated` ha meno di 15 minuti,
    la routine si ferma subito senza fare ricerche né commit) — questa seconda guardia è
    la vera protezione contro chiamate ripetute, e copre anche i doppi/tripli scatti
    "a cascata" causati dal webhook non filtrato per branch (ogni push, incluso quello
    della routine stessa o della GitHub Action di verifica link, fa ripartire una nuova
    esecuzione che però si ferma da sola in ~15 secondi se troppo ravvicinata — comportamento
    verificato dal vivo, inclusa la gestione automatica di un conflitto di push tra due
    esecuzioni quasi simultanee, risolto dalla routine stessa con fetch + cherry-pick).
  - **Token nel Worker**: fine-grained PAT, permesso Contents: Read and write, limitato al
    solo repository `parsing_web`, scadenza consigliata 90 giorni (**da annotare qui la
    data una volta nota**). Essendo solo nelle impostazioni del Worker (mai in un repository
    git, pubblico o privato), non è soggetto alla revoca automatica di GitHub descritta
    sopra. Se scade, il tasto smette di funzionare ma la routine giornaliera continua
    regolarmente (usa la Claude GitHub App, non questo token).
  - **Nota**: durante il primo tentativo di setup è stato creato per errore anche un
    progetto Cloudflare **Pages** (non Workers) collegato al repository, all'indirizzo
    `parsing-web.roberto-modonesi1.workers.dev` — inutilizzato, può essere eliminato dalla
    dashboard Cloudflare quando comodo (nessun impatto se lasciato lì).
- **Verifica link** (`.github/workflows/verify-links.yml` + `scripts/verify_links.py`):
  gira su un runner GitHub Actions normale (internet vero, diverso dalla sandbox della
  routine), automaticamente ad ogni push su `main` che tocca `data.json`. Per ogni annuncio:
  controllo veloce sul formato dell'URL (schema tipico per fonte, es. InfoJobs `/of-i...`,
  Subito `-######.htm`, Adecco con parametro ID, ecc.), poi una richiesta HTTP reale. Se il
  controllo non è conclusivo (403/429/errore di rete — spesso un blocco anti-bot del sito
  sull'IP del runner, non un problema reale del link, confermato empiricamente durante lo
  sviluppo) l'annuncio resta invariato, nessuna penalità. Se il link risulta chiaramente
  scaduto/rimosso (404/410) o rediretto a una pagina generica, viene marcato
  (`linkVerifyFailCount`) e rimosso solo dopo **due controlli falliti consecutivi**, per
  evitare falsi positivi da blocchi temporanei. Nessun token aggiuntivo necessario: usa il
  token automatico dell'Action.

## Pubblicazione

GitHub Pages servito dal branch `main`, root (`/`). Live su
`https://osdgdt.github.io/parsing_web/`.

## Manutenzione

- Per modificare fonti, ruoli, comuni coperti o la logica di scadenza/deduplica: aggiornare
  il prompt della routine cloud (`RemoteTrigger action=update` su
  `trig_01YSFVi49aHWQ2QrZyrVW1Ev`, gestito lato server, non un file in questo repo).
- Per modificare gli schemi URL riconosciuti nella verifica link: `scripts/verify_links.py`,
  dizionario `SPECIFIC_LISTING_PATTERNS`.
- Per ruotare il token del tasto "Aggiorna ora": creare un nuovo fine-grained PAT (stesso
  permesso, stesso repository), aggiornare il secret `GITHUB_PAT` nelle impostazioni del
  Worker Cloudflare (Settings → Variables and Secrets), poi revocare il vecchio token su
  github.com. Non serve toccare `index.html` né fare alcun commit.
- Per modificare la logica del tasto "Aggiorna ora": codice sorgente in
  `cloudflare-worker.js` in questo repo (solo per riferimento/versionamento — va poi
  incollato manualmente nell'editor del Worker su dash.cloudflare.com e ripubblicato, non
  c'è deploy automatico da qui).
