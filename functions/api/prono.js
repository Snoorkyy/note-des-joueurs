// Cloudflare Pages Function — prono « MVP de la journée » (base D1 liée sous le nom DB).
// GET  /api/prono?r=11&dev=X -> {r, mine, n, c:{pid:nb}}   (c : répartition, visible une fois la journée verrouillée)
// POST /api/prono {r, dev, pid}  -> enregistre ou remplace le prono tant que la journée n'a pas commencé
const H = { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*", "access-control-allow-headers": "content-type" };
const J = (o, s = 200, extra = {}) => new Response(JSON.stringify(o), { status: s, headers: { ...H, ...extra } });
let ready = false;
async function init(db) {
  if (ready) return;
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS pronos (r INTEGER NOT NULL, dev TEXT NOT NULL, pid TEXT NOT NULL, ip TEXT, ts INTEGER, PRIMARY KEY (r, dev))"),
    db.prepare("CREATE INDEX IF NOT EXISTS pronos_ip ON pronos (r, ip)"),
  ]);
  ready = true;
}
async function sha(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].slice(0, 10).map(x => x.toString(16).padStart(2, "0")).join("");
}
async function data(request, env) {
  return (await env.ASSETS.fetch(new URL("/data.json", request.url))).json();
}
// verrou : le jour du premier match de la journée, 16 h UTC (17 h à Paris en hiver)
function lockTime(d, r) {
  const days = d.fixtures.filter(f => f[0] === r).map(f => f[1]).sort();
  return days.length ? Date.parse(days[0] + "T16:00:00Z") : 0;
}
export async function onRequestOptions() { return new Response(null, { headers: H }); }
export async function onRequestGet({ request, env }) {
  if (!env.DB) return J({ error: "base non liée" }, 503);
  await init(env.DB);
  const u = new URL(request.url), r = parseInt(u.searchParams.get("r") || "0", 10), dev = u.searchParams.get("dev") || "";
  if (!(r >= 1 && r <= 60)) return J({ error: "journée" }, 400);
  const d = await data(request, env);
  const locked = Date.now() >= lockTime(d, r);
  const tot = await env.DB.prepare("SELECT COUNT(*) n FROM pronos WHERE r=?").bind(r).first();
  const me = /^[A-Za-z0-9-]{16,64}$/.test(dev) ? await env.DB.prepare("SELECT pid FROM pronos WHERE r=? AND dev=?").bind(r, dev).first() : null;
  const c = {};
  if (locked) {
    const { results } = await env.DB.prepare("SELECT pid, COUNT(*) n FROM pronos WHERE r=? GROUP BY pid").bind(r).all();
    for (const x of results) c[x.pid] = x.n;
  }
  return J({ r, locked, lock: lockTime(d, r), mine: me ? me.pid : null, n: tot.n, c }, 200, { "cache-control": "no-store" });
}
export async function onRequestPost({ request, env }) {
  if (!env.DB) return J({ error: "base non liée" }, 503);
  await init(env.DB);
  let b; try { b = await request.json(); } catch (e) { return J({ error: "json" }, 400); }
  const { r, dev, pid } = b || {};
  if (!Number.isInteger(r) || !/^[A-Za-z0-9-]{16,64}$/.test(dev || "") || !/^P\d{6}$/.test(pid || "")) return J({ error: "requête" }, 400);
  const d = await data(request, env);
  if (Date.now() >= lockTime(d, r)) return J({ error: "pronos fermés pour cette journée" }, 409);
  const clubs = new Set(d.fixtures.filter(f => f[0] === r).flatMap(f => [f[2], f[3]]));
  const pl = d.players[pid];
  if (!pl || !clubs.has(pl.club)) return J({ error: "joueur hors journée" }, 400);
  const ip = await sha((request.headers.get("cf-connecting-ip") || "") + "|elf");
  const c = await env.DB.prepare("SELECT COUNT(*) n FROM pronos WHERE r=? AND ip=? AND dev<>?").bind(r, ip, dev).first();
  if (c.n >= 6) return J({ error: "trop de pronos depuis cette connexion" }, 429);
  await env.DB.prepare("INSERT OR REPLACE INTO pronos (r, dev, pid, ip, ts) VALUES (?,?,?,?,?)").bind(r, dev, pid, ip, Date.now()).run();
  return onRequestGet({ request: new Request(new URL(`/api/prono?r=${r}&dev=${dev}`, request.url)), env });
}
