// Cloudflare Pages Function — partage du visuel « Mes notes » d'un lecteur.
// /s/<id>.jpg -> l'image ; /s/<id> -> page avec carte X (summary_large_image) qui redirige vers la page de vote du match.
const SITE = "https://note-des-joueurs.pages.dev";
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
export async function onRequestGet({ params, env, request }) {
  const p = String(params.id || "");
  const jpg = p.endsWith(".jpg"), id = p.replace(/\.jpg$/, "");
  if (!/^[a-z0-9]{6,12}$/.test(id) || !env.DB) return Response.redirect(SITE + "/vote.html", 302);
  let row = null;
  try { row = await env.DB.prepare(jpg ? "SELECT img FROM shares WHERE id=?" : "SELECT m FROM shares WHERE id=?").bind(id).first(); } catch (e) {}
  if (!row) return jpg ? new Response("introuvable", { status: 404 }) : Response.redirect(SITE + "/vote.html", 302);
  if (jpg) return new Response(new Uint8Array(row.img), { headers: { "content-type": "image/jpeg", "cache-control": "public, max-age=86400" } });
  let title = "Mes notes du match · À toi de noter !";
  try {
    const d = await (await env.ASSETS.fetch(new URL("/data.json", request.url))).json();
    const g = d.matches.find(x => x.id === row.m);
    if (g) title = `Mes notes : ${d.clubs[g.home].name} ${g.hs}-${g.as} ${d.clubs[g.away].name} · À toi de noter !`;
  } catch (e) {}
  const desc = "Mets tes notes aux joueurs du match et compare avec EuroLeague France et les autres lecteurs.";
  const dest = `${SITE}/vote.html?m=${row.m}`, img = `${SITE}/s/${id}.jpg`;
  const html = `<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>${esc(title)}</title>
<meta name="description" content="${desc}"><meta property="og:type" content="article"><meta property="og:site_name" content="EuroLeague France">
<meta property="og:title" content="${esc(title)}"><meta property="og:description" content="${desc}"><meta property="og:url" content="${SITE}/s/${id}">
<meta property="og:image" content="${img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="${esc(title)}"><meta name="twitter:description" content="${desc}"><meta name="twitter:image" content="${img}">
<meta http-equiv="refresh" content="0; url=${dest}"></head><body style="background:#060D24;color:#fff;font-family:sans-serif;text-align:center;padding:40px">
<p><a style="color:#FFB547" href="${dest}">À toi de noter les joueurs du match</a></p><script>location.replace(${JSON.stringify(dest)})</script></body></html>`;
  return new Response(html, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=300" } });
}
