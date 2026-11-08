// Cloudflare Pages Function — classements des jeux (base D1 liée sous le nom DB).
// Pas d'inscription : chaque appareil a un identifiant anonyme (dev, déjà utilisé par le vote) et un pseudo automatique modifiable.
// L'adresse IP n'est conservée que sous forme d'empreinte, pour limiter les abus.
//
// GET  /api/scores?dev=X&g=pm|qui|maillot|av|myst|cinq|prono[&k=..]  -> {g, k, n, top:[{p,s,x}], me:{r,s}, pseudo}
// GET  /api/scores?dev=X&me=1                                      -> {pseudo}
// GET  /api/scores?mystere=1                                       -> {date, num, t}  (joueur mystère du jour, codé)
// POST /api/scores {dev, pseudo}                                   -> change le pseudo
// POST /api/scores {dev, g, ...}                                   -> enregistre un score (vérifié avec data.json)
const H = { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*", "access-control-allow-headers": "content-type" };
const J = (o, s = 200, extra = {}) => new Response(JSON.stringify(o), { status: s, headers: { ...H, "cache-control": "no-store", ...extra } });
const DEV = /^[A-Za-z0-9-]{16,64}$/;
let ready = false;
async function init(db) {
  if (ready) return;
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS joueurs (dev TEXT PRIMARY KEY, pseudo TEXT, ip TEXT, ts INTEGER)"),
    db.prepare("CREATE TABLE IF NOT EXISTS scores (g TEXT NOT NULL, k TEXT NOT NULL, dev TEXT NOT NULL, s REAL NOT NULL, n INTEGER DEFAULT 1, ip TEXT, ts INTEGER, PRIMARY KEY (g, k, dev))"),
    db.prepare("CREATE INDEX IF NOT EXISTS scores_gk ON scores (g, k, s)"),
    db.prepare("CREATE TABLE IF NOT EXISTS mystere (d TEXT PRIMARY KEY, pid TEXT NOT NULL)"),
  ]);
  ready = true;
}
async function sha(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
}
const autoPseudo = async dev => "Fan " + (parseInt((await sha(dev + "|pseudo")).slice(0, 6), 16) % 9000 + 1000);
const today = () => new Intl.DateTimeFormat("fr-CA", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());

// ---------- données (mêmes calculs que la page des jeux) ----------
let CACHE = null;
async function data(request, env) {
  if (CACHE && Date.now() - CACHE.t < 60000) return CACHE.d;
  const d = await (await env.ASSETS.fetch(new URL("/data.json", request.url))).json();
  const ST = {};
  for (const [p, m, c, min, ev, pm, note] of d.notes) { const s = ST[p] || (ST[p] = { n: 0, note: 0, ev: 0 }); s.n++; s.note += note; s.ev += ev; }
  for (const p in ST) { const s = ST[p]; s.note /= s.n; s.ev /= s.n; s.club = d.players[p] ? d.players[p].club : null; s.pos = ((d.fantasy && d.fantasy.p && d.fantasy.p[p]) || [])[0] || null; }
  const played = d.matches.filter(m => m.hs != null);
  d._ST = ST; d._last = Math.max(...played.map(m => m.round)); d._played = played; d._photos = new Set(d.photos || []);
  CACHE = { t: Date.now(), d };
  return d;
}
const fnv = s => { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };
async function mysteryOf(db, d, date) {
  const row = await db.prepare("SELECT pid FROM mystere WHERE d=?").bind(date).first();
  if (row) return row.pid;
  const pool = Object.keys(d._ST).filter(p => d.players[p] && d._ST[p].n >= 5 && d._photos.has(p) && d._ST[p].pos).sort();
  const pid = pool[fnv("elf-mystere-" + date) % pool.length];
  await db.prepare("INSERT OR IGNORE INTO mystere (d, pid) VALUES (?,?)").bind(date, pid).run();
  return (await db.prepare("SELECT pid FROM mystere WHERE d=?").bind(date).first()).pid;
}
const code = pid => btoa(pid.split("").reverse().join("") + "|elf").replace(/=+$/, "");
// classement à l'aveugle : même barème que le jeu (distance de Spearman sur 100, ex aequo à 0,05 près)
function avScore(order, ST) {
  const N = order.length, TOL = 0.049, unit = 100 / Math.floor(N * N / 2);
  const pick = order.map(([p]) => ({ p, avg: ST[p].note }));
  let F = 0;
  for (const [p, s] of order) { const a = ST[p].note; const lo = 1 + pick.filter(o => o.avg > a + TOL).length, hi = pick.filter(o => o.avg >= a - TOL).length; F += s < lo ? lo - s : s > hi ? s - hi : 0; }
  return Math.max(0, Math.round(100 - unit * F));
}
const MAXG = 8;

// ---------- lecture ----------
async function board(env, d, g, k, dev) {
  const db = env.DB;
  let rows;
  if (g === "prono") {
    // points = journées où le prono était le MVP (meilleure note de la journée)
    const mvp = {};
    for (let r = 1; r <= d._last; r++) {
      const ids = new Set(d._played.filter(m => m.round === r).map(m => m.id));
      const rn = d.notes.filter(n => ids.has(n[1])); if (!rn.length) continue;
      const top = Math.max(...rn.map(n => n[6])); mvp[r] = new Set(rn.filter(n => n[6] === top).map(n => n[0]));
    }
    const { results } = await db.prepare("SELECT r, dev, pid FROM pronos").all().catch(() => ({ results: [] }));
    const acc = {};
    for (const x of results) { if (!mvp[x.r]) continue; const a = acc[x.dev] || (acc[x.dev] = { s: 0, n: 0 }); a.n++; if (mvp[x.r].has(x.pid)) a.s++; }
    rows = Object.entries(acc).map(([dv, a]) => ({ dev: dv, s: a.s, x: a.n }));
  } else if ((g === "myst" || g === "cinq") && k === "saison") {
    const { results } = await db.prepare("SELECT dev, SUM(s) s, COUNT(*) x FROM scores WHERE g=? GROUP BY dev").bind(g).all();
    rows = results;
  } else {
    const { results } = await db.prepare("SELECT dev, s, n x FROM scores WHERE g=? AND k=?").bind(g, k).all();
    rows = results;
  }
  rows.sort((a, b) => b.s - a.s || (g === "myst" || g === "cinq" ? 0 : b.x - a.x));
  const top = rows.slice(0, 10);
  const devs = [...new Set([...top.map(r => r.dev), dev].filter(Boolean))];
  const names = {};
  if (devs.length) {
    const { results } = await db.prepare(`SELECT dev, pseudo FROM joueurs WHERE dev IN (${devs.map(() => "?").join(",")})`).bind(...devs).all();
    for (const r of results) names[r.dev] = r.pseudo;
  }
  for (const dv of devs) if (!names[dv]) names[dv] = await autoPseudo(dv);
  const i = rows.findIndex(r => r.dev === dev);
  return {
    g, k, n: rows.length,
    top: top.map((r, j) => ({ r: j + 1, p: names[r.dev], s: Math.round(r.s * 10) / 10, x: r.x, me: r.dev === dev })),
    me: i >= 0 ? { r: i + 1, s: Math.round(rows[i].s * 10) / 10, x: rows[i].x } : null,
    pseudo: dev ? names[dev] : null,
  };
}

export async function onRequestOptions() { return new Response(null, { headers: H }); }
export async function onRequestGet({ request, env }) {
  if (!env.DB) return J({ error: "base non liée" }, 503);
  await init(env.DB);
  const u = new URL(request.url), q = k => u.searchParams.get(k) || "";
  const dev = DEV.test(q("dev")) ? q("dev") : null;
  const d = await data(request, env);
  if (q("mystere")) {
    const date = today(), pid = await mysteryOf(env.DB, d, date);
    return J({ date, num: Math.round((Date.parse(date) - Date.parse("2026-11-08")) / 864e5) + 1, t: code(pid) });
  }
  if (q("me")) {
    if (!dev) return J({ error: "appareil" }, 400);
    const r = await env.DB.prepare("SELECT pseudo FROM joueurs WHERE dev=?").bind(dev).first();
    return J({ pseudo: (r && r.pseudo) || await autoPseudo(dev) });
  }
  const g = q("g");
  if (!["pm", "qui", "maillot", "av", "myst", "cinq", "prono"].includes(g)) return J({ error: "jeu" }, 400);
  let k = q("k") || "saison";
  if (g === "myst" && k === "jour") k = today();
  if (g === "cinq" && k === "journee") k = String(d._last);
  return J(await board(env, d, g, k, dev));
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return J({ error: "base non liée" }, 503);
  await init(env.DB);
  let b; try { b = await request.json(); } catch (e) { return J({ error: "json" }, 400); }
  const dev = b && b.dev;
  if (!DEV.test(dev || "")) return J({ error: "appareil" }, 400);
  const ip = (await sha((request.headers.get("cf-connecting-ip") || "") + "|elf")).slice(0, 20), ts = Date.now(), db = env.DB;

  if (typeof b.pseudo === "string") {
    const p = b.pseudo.trim().replace(/\s+/g, " ");
    if (!/^[\p{L}\p{N} ._'-]{2,20}$/u.test(p)) return J({ error: "Pseudo : 2 à 20 lettres ou chiffres" }, 400);
    const taken = await db.prepare("SELECT dev FROM joueurs WHERE lower(pseudo)=lower(?) AND dev<>?").bind(p, dev).first();
    if (taken) return J({ error: "Ce pseudo est déjà pris" }, 409);
    await db.prepare("INSERT INTO joueurs (dev, pseudo, ip, ts) VALUES (?,?,?,?) ON CONFLICT(dev) DO UPDATE SET pseudo=excluded.pseudo, ts=excluded.ts").bind(dev, p, ip, ts).run();
    return J({ pseudo: p });
  }

  // garde-fou : 8 appareils max par connexion et par jour pour un même jeu
  const g = b.g, d = await data(request, env), ST = d._ST;
  const many = await db.prepare("SELECT COUNT(DISTINCT dev) n FROM scores WHERE g=? AND ip=? AND dev<>? AND ts>?").bind(g, ip, dev, ts - 864e5).first();
  if (many.n >= 8) return J({ error: "trop d'appareils depuis cette connexion" }, 429);
  const best = async (k, s) => {
    await db.prepare("INSERT INTO scores (g, k, dev, s, n, ip, ts) VALUES (?,?,?,?,1,?,?) ON CONFLICT(g, k, dev) DO UPDATE SET s=MAX(s, excluded.s), n=n+1, ts=excluded.ts").bind(g, k, dev, s, ip, ts).run();
  };
  const once = async (k, s) => {
    await db.prepare("INSERT OR IGNORE INTO scores (g, k, dev, s, n, ip, ts) VALUES (?,?,?,?,1,?,?)").bind(g, k, dev, s, ip, ts).run();
  };
  const ok5 = p => ST[p] && ST[p].n >= 5;

  if (g === "pm") {
    // série : chaque duel [choisi, autre] doit être juste (meilleure moyenne de notes)
    const run = Array.isArray(b.run) ? b.run.slice(0, 1000) : [];
    if (!run.every(x => Array.isArray(x) && ok5(x[0]) && ok5(x[1]) && x[0] !== x[1] && ST[x[0]].note > ST[x[1]].note)) return J({ error: "série invalide" }, 400);
    await best("saison", run.length);
  } else if (g === "maillot") {
    const run = Array.isArray(b.run) ? b.run.slice(0, 1000) : [];
    if (!run.every(x => Array.isArray(x) && ST[x[0]] && ST[x[0]].club === x[1])) return J({ error: "série invalide" }, 400);
    await best("saison", run.length);
  } else if (g === "qui") {
    const run = Array.isArray(b.run) ? b.run.slice(0, 1000) : [];
    if (!run.every(p => ok5(p))) return J({ error: "série invalide" }, 400);
    await best("saison", run.length);
  } else if (g === "av") {
    // classement à l'aveugle : score recalculé ici à partir du placement
    const order = Array.isArray(b.order) ? b.order : [];
    const N = order.length, mg = Math.max(1, Math.ceil(d._last / 2));
    const places = new Set(order.map(x => x[1]));
    if (![5, 10].includes(N) || places.size !== N || ![...places].every(s => s >= 1 && s <= N) || new Set(order.map(x => x[0])).size !== N || !order.every(x => ST[x[0]] && ST[x[0]].n >= mg)) return J({ error: "partie invalide" }, 400);
    await best("saison", avScore(order, ST));
  } else if (g === "myst") {
    const date = today(), pid = await mysteryOf(db, d, date);
    const gs = Array.isArray(b.guesses) ? b.guesses.slice(0, MAXG) : [];
    if (!gs.length || !gs.every(p => ST[p])) return J({ error: "essais invalides" }, 400);
    const k = gs.indexOf(pid);
    const done = k >= 0 || gs.length >= MAXG;
    if (!done) return J({ error: "partie non terminée" }, 400);
    await once(date, k >= 0 ? MAXG + 1 - (k + 1) : 0);
  } else if (g === "cinq") {
    const R = d._last, ids = new Set(d._played.filter(m => m.round === R).map(m => m.id));
    const rows = {}; for (const n of d.notes) if (ids.has(n[1]) && n[3] >= 10) rows[n[0]] = n;
    const picks = Array.isArray(b.picks) ? b.picks : [];
    const cnt = {}; for (const p of picks) if (rows[p]) cnt[rows[p][2]] = (cnt[rows[p][2]] || 0) + 1;
    if (picks.length !== 5 || new Set(picks).size !== 5 || !picks.every(p => rows[p]) || Object.values(cnt).some(c => c > 2)) return J({ error: "5 invalide" }, 400);
    await once(String(R), picks.reduce((s, p) => s + rows[p][6], 0));
  } else return J({ error: "jeu" }, 400);

  const k = g === "myst" ? "saison" : g === "cinq" ? String(d._last) : "saison";
  return J(await board(env, d, g, k, dev));
}
