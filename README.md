# parsing_web — Lavoro a Brescia

Pagina statica che mostra offerte di lavoro (cameriera / commessa / barista / cassiera /
cucina / reception) a Brescia e dintorni (~10 km), aggiornata automaticamente una volta al
giorno da una routine cloud (Claude schedule/RemoteTrigger).

## Come funziona

- `index.html` — pagina statica (HTML/CSS/JS vanilla), legge `data.json` e mostra le
  offerte con filtri lato client (ruolo, tipo contratto, "solo nuovi di oggi"). Non va
  mai modificata dalla routine giornaliera.
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
        "location": "string",
        "url": "string",
        "source": "string (es. Indeed, InfoJobs, ...)",
        "salary": "string o null",
        "contractType": "tempo-pieno|part-time|weekend-sera|indifferente",
        "datePosted": "ISO 8601 o null",
        "description": "string breve",
        "firstSeen": "ISO 8601 (data prima comparsa)",
        "lastSeen": "ISO 8601 (data ultima volta trovato nelle ricerche)"
      }
    ]
  }
  ```
- La routine giornaliera cerca su Indeed, InfoJobs, Subito.it, Bakeca, Adecco, Randstad,
  Gi Group, Borsa Lavoro Regione Lombardia (+ LinkedIn best-effort), aggiorna/aggiunge
  annunci in `data.json`, fa scadere quelli non più visti da oltre ~21 giorni, poi fa
  commit + push. GitHub Pages ripubblica automaticamente.

## Pubblicazione

GitHub Pages servito dal branch `main`, root (`/`).

## Manutenzione

Per modificare fonti, ruoli, comuni coperti o la logica di scadenza, aggiornare il prompt
della routine cloud (gestito tramite la skill "schedule" / RemoteTrigger di Claude, non un
file in questo repo).
