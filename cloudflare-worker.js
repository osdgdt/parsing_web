// Worker per il tasto "Aggiorna ora" di https://osdgdt.github.io/parsing_web/
// Riceve un semplice POST dal bottone sulla pagina pubblica, e usa il token
// GitHub (salvato come "secret" del Worker, mai nel codice) per far scattare
// la routine di ricerca tramite un push sul branch refresh-trigger.
//
// Il token va aggiunto in: Worker > Settings > Variables and Secrets >
// Add > tipo "Secret", nome GITHUB_PAT, valore = il token fine-grained
// (Contents: Read and write, solo repo parsing_web).

const GH_OWNER = "osdgdt";
const GH_REPO = "parsing_web";
const BRANCH = "refresh-trigger";
const FILE = "trigger.json";

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const headers = {
      "Authorization": `Bearer ${env.GITHUB_PAT}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "lavoro-brescia-refresh-worker",
    };
    const contentsUrl = `https://api.github.com/repos/${GH_OWNER}/${GH_REPO}/contents/${FILE}`;
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Content-Type": "application/json",
    };

    try {
      const getRes = await fetch(`${contentsUrl}?ref=${BRANCH}`, { headers });
      if (!getRes.ok) {
        return new Response(JSON.stringify({ ok: false, step: "get", status: getRes.status }), {
          status: 502,
          headers: corsHeaders,
        });
      }
      const current = await getRes.json();
      const content = btoa(
        JSON.stringify({ lastTriggeredAt: new Date().toISOString() }, null, 2) + "\n"
      );

      const putRes = await fetch(contentsUrl, {
        method: "PUT",
        headers,
        body: JSON.stringify({
          message: "Richiesta aggiornamento dal tasto sulla pagina",
          content,
          sha: current.sha,
          branch: BRANCH,
        }),
      });

      return new Response(JSON.stringify({ ok: putRes.ok }), {
        status: putRes.ok ? 200 : 502,
        headers: corsHeaders,
      });
    } catch (e) {
      return new Response(JSON.stringify({ ok: false, error: String(e) }), {
        status: 500,
        headers: corsHeaders,
      });
    }
  },
};
