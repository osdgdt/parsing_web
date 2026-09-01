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
- **Tasto "Aggiorna ora"** (in `index.html`): chiama `POST /repos/osdgdt/parsing_web/dispatches`
  con `event_type: "refresh-requested"`, usando un fine-grained Personal Access Token
  incorporato nel codice JS della pagina, con permesso **Contents: Read and write** limitato
  a questo solo repository (è il permesso minimo che GitHub richiede per questo endpoint,
  non esiste un permesso più granulare "solo dispatch"). Un webhook trigger collegato alla
  routine (`RemoteTrigger action=create_webhook_trigger`, evento `repository_dispatch`) fa
  scattare la stessa routine giornaliera. Protezioni anti-abuso: cooldown di 15 minuti lato
  pagina (solo UX, non sicurezza) + guardia lato routine (passo 0 del prompt: se
  `lastUpdated` ha meno di 15 minuti, la routine si ferma subito senza fare nulla) — questa
  seconda guardia è la vera protezione contro chiamate ripetute all'API.
  - **Token**: creato manualmente su github.com (Settings, poi Developer settings, poi
    Fine-grained tokens), scadenza consigliata 90 giorni. **Data di creazione/scadenza da
    annotare qui una volta creato.** Se scade, il tasto smette di funzionare ma la routine
    giornaliera continua regolarmente (usa la Claude GitHub App, non questo token).
  - **Rischio noto e accettato**: essendo nel codice JS di una pagina pubblica, chiunque
    legga il sorgente della pagina potrebbe estrarre il token e usarlo per scrivere
    direttamente nel repository (non solo per lanciare aggiornamenti), perché il permesso
    concesso è più ampio di un ipotetico permesso "solo dispatch" che GitHub non offre. Il
    repository non contiene dati sensibili; un'eventuale manomissione sarebbe comunque
    visibile e reversibile nella cronologia git. Non è stata aggiunta una protezione sul
    branch `main` per bloccare questo scenario: configurarla in modo sicuro richiederebbe
    identificare con precisione le identità con cui la routine e la GitHub Action fanno
    push, con il rischio concreto di bloccare per errore l'automazione legittima — un
    rischio giudicato non proporzionato al beneficio per un sito pubblico a basso rischio
    come questo.
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
  permesso, stesso repository), sostituire il valore di `REFRESH_TOKEN` in `index.html`,
  fare commit/push, revocare il vecchio token su github.com.
