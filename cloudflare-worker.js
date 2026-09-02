// Worker per i controlli self-service di https://osdgdt.github.io/parsing_web/
// Riceve un semplice POST dalla pagina pubblica (corpo testo/JSON, senza header
// personalizzati - così il browser non fa una richiesta di preflight CORS) e usa
// il token GitHub (salvato come "secret" del Worker, mai nel codice) per scrivere
// nel repository al posto della pagina.
//
// Azioni supportate (campo "action" nel corpo JSON; nessun corpo o azione non
// riconosciuta = "refresh", per compatibilità con la versione precedente):
//   (nessuna / "refresh")            -> push su trigger.json (branch refresh-trigger),
//                                        fa scattare una nuova ricerca
//   {"action":"add_role","label":".."}   -> aggiunge una mansione a roles.json (branch main)
//   {"action":"remove_role","key":".."}  -> rimuove una mansione da roles.json (branch main)
//
// Il token va aggiunto in: Worker > Settings > Variables and Secrets >
// Add > tipo "Secret", nome GITHUB_PAT, valore = il token fine-grained
// (Contents: Read and write, solo repo parsing_web).

const GH_OWNER = "osdgdt";
const GH_REPO = "parsing_web";
const REFRESH_BRANCH = "refresh-trigger";
const REFRESH_FILE = "trigger.json";
const MAIN_BRANCH = "main";
const ROLES_FILE = "roles.json";
const MAX_CUSTOM_ROLES = 25;
const MAX_LABEL_LENGTH = 40;

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Content-Type": "application/json",
    };

    let body = {};
    try {
      const text = await request.text();
      if (text) body = JSON.parse(text);
    } catch (e) {
      return json({ ok: false, error: "corpo non valido" }, 400, corsHeaders);
    }
    const action = body.action || "refresh";

    const headers = {
      "Authorization": `Bearer ${env.GITHUB_PAT}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "lavoro-brescia-worker",
    };

    try {
      if (action === "refresh") {
        return await handleRefresh(headers, corsHeaders);
      }
      if (action === "add_role") {
        return await handleRoleChange(headers, corsHeaders, (roles) => addRole(roles, body.label));
      }
      if (action === "remove_role") {
        return await handleRoleChange(headers, corsHeaders, (roles) => removeRole(roles, body.key));
      }
      return json({ ok: false, error: "azione sconosciuta" }, 400, corsHeaders);
    } catch (e) {
      return json({ ok: false, error: String(e) }, 500, corsHeaders);
    }
  },
};

function json(obj, status, headers) {
  return new Response(JSON.stringify(obj), { status, headers });
}

function utf8ToBase64(str) {
  const bytes = new TextEncoder().encode(str);
  let binary = "";
  bytes.forEach((b) => { binary += String.fromCharCode(b); });
  return btoa(binary);
}

function base64ToUtf8(b64) {
  const binary = atob(b64);
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function slugify(label) {
  return label
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, MAX_LABEL_LENGTH);
}

async function getFile(path, branch, headers) {
  const url = `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/contents/${path}?ref=${branch}`;
  const res = await fetch(url, { headers });
  if (!res.ok) return null;
  const data = await res.json();
  return { sha: data.sha, content: JSON.parse(base64ToUtf8(data.content)) };
}

function putFile(path, branch, headers, content, sha, message) {
  const url = `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/contents/${path}`;
  return fetch(url, {
    method: "PUT",
    headers,
    body: JSON.stringify({
      message,
      content: utf8ToBase64(JSON.stringify(content, null, 2) + "\n"),
      sha,
      branch,
    }),
  });
}

async function handleRefresh(headers, corsHeaders) {
  const file = await getFile(REFRESH_FILE, REFRESH_BRANCH, headers);
  if (!file) return json({ ok: false, step: "get" }, 502, corsHeaders);
  const res = await putFile(
    REFRESH_FILE,
    REFRESH_BRANCH,
    headers,
    { lastTriggeredAt: new Date().toISOString() },
    file.sha,
    "Richiesta aggiornamento dal tasto sulla pagina"
  );
  return json({ ok: res.ok }, res.ok ? 200 : 502, corsHeaders);
}

async function handleRoleChange(headers, corsHeaders, mutate) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const file = await getFile(ROLES_FILE, MAIN_BRANCH, headers);
    if (!file) return json({ ok: false, step: "get" }, 502, corsHeaders);

    const result = mutate(file.content);
    if (!result.changed) {
      return json({ ok: true, noop: true, reason: result.reason }, 200, corsHeaders);
    }

    const res = await putFile(ROLES_FILE, MAIN_BRANCH, headers, result.roles, file.sha, result.message);
    if (res.ok) return json({ ok: true }, 200, corsHeaders);
    if (res.status === 409 && attempt < 2) continue; // conflitto (due modifiche quasi simultanee), riprova
    return json({ ok: false, step: "put", status: res.status }, 502, corsHeaders);
  }
  return json({ ok: false, step: "retries-exhausted" }, 502, corsHeaders);
}

function addRole(rolesFile, rawLabel) {
  const label = (rawLabel || "").trim().slice(0, MAX_LABEL_LENGTH);
  if (!label) return { changed: false, reason: "etichetta vuota" };
  const key = slugify(label);
  if (!key || key === "tutti") return { changed: false, reason: "etichetta non valida" };

  const existingKeys = new Set([
    ...rolesFile.builtin.map((r) => r.key),
    ...rolesFile.custom.map((r) => r.key),
  ]);
  if (existingKeys.has(key)) return { changed: false, reason: "già presente" };
  if (rolesFile.custom.length >= MAX_CUSTOM_ROLES) {
    return { changed: false, reason: "limite massimo di mansioni raggiunto" };
  }

  rolesFile.custom.push({ key, label, addedAt: new Date().toISOString() });
  return { changed: true, roles: rolesFile, message: `Aggiunta mansione: ${label}` };
}

function removeRole(rolesFile, key) {
  const idx = rolesFile.custom.findIndex((r) => r.key === key);
  if (idx === -1) return { changed: false, reason: "non trovata" };
  const removed = rolesFile.custom[idx];
  rolesFile.custom.splice(idx, 1);
  return { changed: true, roles: rolesFile, message: `Rimossa mansione: ${removed.label}` };
}
