// Cloudflare Pages Function — vote des lecteurs (base D1 liée sous le nom DB).
// GET  /api/vote?m=E2026-99  -> {m, p:{pid:[moyenne, nb]}, n:votants}
// GET  /api/vote             -> {a:{"E2026-99":{pid:[moyenne, nb]}}}  (toutes les moyennes, pour la page des notes)
// POST /api/vote {m, dev, v:{pid:note}}  -> enregistre (1 vote par appareil, par joueur, par match ; le premier compte)
const H = { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*", "access-control-allow-headers": "content-type" };
const J = (o, s = 200, extra = {}) => new Response(JSON.stringify(o), { status: s, headers: { ...H, ...extra } });
let ready = false;
async function init(db) {
  if (ready) return;
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS votes (m TEXT NOT NULL, dev TEXT NOT NULL, pid TEXT NOT NULL, note REAL NOT NULL, ip TEXT, ts INTEGER, PRIMARY KEY (m, dev, pid))"),
    db.prepare("CREATE INDEX IF NOT EXISTS votes_ip ON votes (m, ip)"),
  ]);
  ready = true;
}
const r1 = x => Math.round(x * 10) / 10;
async function sha(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].slice(0, 10).map(x => x.toString(16).padStart(2, "0")).join("");
}
export async function onRequestOptions() { return new Response(null, { headers: H }); }
export async function onRequestGet({ request, env }) {
  if (!env.DB) return J({ error: "base non liée" }, 503);
  await init(env.DB);
  const m = new URL(request.url).searchParams.get("m");
  if (m) {
    if (!/^E\d{4}-\d{1,3}$/.test(m)) return J({ error: "match" }, 400);
    const { results } = await env.DB.prepare("SELECT pid, AVG(note) a, COUNT(*) n FROM votes WHERE m=? GROUP BY pid").bind(m).all();
    const v = await env.DB.prepare("SELECT COUNT(DISTINCT dev) n FROM votes WHERE m=?").bind(m).first();
    const p = {}; for (const r of results) p[r.pid] = [r1(r.a), r.n];
    return J({ m, p, n: v.n }, 200, { "cache-control": "no-store" });
  }
  const { results } = await env.DB.prepare("SELECT m, pid, AVG(note) a, COUNT(*) n FROM votes GROUP BY m, pid").all();
  const a = {}; for (const r of results) (a[r.m] ||= {})[r.pid] = [r1(r.a), r.n];
  return J({ a }, 200, { "cache-control": "public, max-age=60" });
}
export async function onRequestPost({ request, env }) {
  if (!env.DB) return J({ error: "base non liée" }, 503);
  await init(env.DB);
  let b; try { b = await request.json(); } catch (e) { return J({ error: "json" }, 400); }
  const { m, dev, v } = b || {};
  if (!/^E\d{4}-\d{1,3}$/.test(m || "") || !/^[A-Za-z0-9-]{16,64}$/.test(dev || "") || !v || typeof v !== "object") return J({ error: "requête" }, 400);
  // joueurs autorisés : ceux du match avec 10 min ou plus (lus dans data.json du site)
  const d = await (await env.ASSETS.fetch(new URL("/data.json", request.url))).json();
  const ok = new Set(d.notes.filter(n => n[1] === m && n[3] >= 10).map(n => n[0]));
  if (!ok.size) return J({ error: "match inconnu" }, 404);
  const ent = Object.entries(v).filter(([p, x]) => ok.has(p) && typeof x === "number" && x >= 0 && x <= 10 && Math.round(x * 2) === x * 2);
  if (!ent.length) return J({ error: "aucune note valable" }, 400);
  const ip = await sha((request.headers.get("cf-connecting-ip") || "") + "|elf");
  // garde-fou contre le bourrage : 6 appareils max par adresse IP et par match
  const c = await env.DB.prepare("SELECT COUNT(DISTINCT dev) n FROM votes WHERE m=? AND ip=? AND dev<>?").bind(m, ip, dev).first();
  if (c.n >= 6) return J({ error: "trop de votes depuis cette connexion" }, 429);
  const ts = Date.now();
  await env.DB.batch(ent.map(([p, x]) => env.DB.prepare("INSERT OR IGNORE INTO votes (m, dev, pid, note, ip, ts) VALUES (?,?,?,?,?,?)").bind(m, dev, p, x, ip, ts)));
  return onRequestGet({ request: new Request(new URL("/api/vote?m=" + m, request.url)), env });
}
