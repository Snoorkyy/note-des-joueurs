// Cloudflare Pages Function — jeux EuroLeague France : classements, collection de cartes, grille, trios, l'intrus (base D1 « DB »).
// Pas d'inscription : chaque appareil a un identifiant anonyme (dev, déjà utilisé par le vote) et un pseudo automatique modifiable.
// L'adresse IP n'est conservée que sous forme d'empreinte, pour limiter les abus.
import { buildST, makeGrid, makeTrios, gridOk, intrusWhy, tierMap, collectible, rng } from "../../jeux/logic.js";

const H = { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*", "access-control-allow-headers": "content-type" };
const J = (o, s = 200, extra = {}) => new Response(JSON.stringify(o), { status: s, headers: { ...H, "cache-control": "no-store", ...extra } });
const DEV = /^[A-Za-z0-9-]{16,64}$/;
const GAMES = ["pm", "qui", "maillot", "av", "myst", "cinq", "prono", "grille", "intrus", "col"];
let ready = false;
async function init(db) {
  if (ready) return;
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS joueurs (dev TEXT PRIMARY KEY, pseudo TEXT, ip TEXT, ts INTEGER)"),
    db.prepare("CREATE TABLE IF NOT EXISTS scores (g TEXT NOT NULL, k TEXT NOT NULL, dev TEXT NOT NULL, s REAL NOT NULL, n INTEGER DEFAULT 1, ip TEXT, ts INTEGER, PRIMARY KEY (g, k, dev))"),
    db.prepare("CREATE INDEX IF NOT EXISTS scores_gk ON scores (g, k, s)"),
    db.prepare("CREATE TABLE IF NOT EXISTS mystere (d TEXT PRIMARY KEY, pid TEXT NOT NULL)"),
    db.prepare("CREATE TABLE IF NOT EXISTS jour (d TEXT NOT NULL, k TEXT NOT NULL, v TEXT NOT NULL, PRIMARY KEY (d, k))"),
    db.prepare("CREATE TABLE IF NOT EXISTS collection (dev TEXT NOT NULL, pid TEXT NOT NULL, src TEXT, ts INTEGER, PRIMARY KEY (dev, pid))"),
    db.prepare("CREATE TABLE IF NOT EXISTS packs (dev TEXT NOT NULL, d TEXT NOT NULL, v TEXT, PRIMARY KEY (dev, d))"),
    db.prepare("CREATE TABLE IF NOT EXISTS trio_rep (d TEXT NOT NULL, i INTEGER NOT NULL, dev TEXT NOT NULL, t TEXT, r TEXT, v TEXT, ts INTEGER, PRIMARY KEY (d, i, dev))"),
    db.prepare("CREATE TABLE IF NOT EXISTS grille_rep (d TEXT NOT NULL, cell TEXT NOT NULL, dev TEXT NOT NULL, pid TEXT, PRIMARY KEY (d, cell, dev))"),
  ]);
  ready = true;
}
async function sha(s) {
  const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
}
const autoPseudo = async dev => "Fan " + (parseInt((await sha(dev + "|pseudo")).slice(0, 6), 16) % 9000 + 1000);
const today = () => new Intl.DateTimeFormat("fr-CA", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());

// ---------- données ----------
let CACHE = null;
async function data(request, env) {
  if (CACHE && Date.now() - CACHE.t < 60000) return CACHE.d;
  const d = await (await env.ASSETS.fetch(new URL("/data.json", request.url))).json();
  const played = d.matches.filter(m => m.hs != null);
  d._ST = buildST(d); d._last = Math.max(...played.map(m => m.round)); d._played = played; d._photos = new Set(d.photos || []);
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
// grille et trios du jour : figés en base au premier appel (les données peuvent changer dans la journée)
async function jour(db, d, date) {
  const rows = (await db.prepare("SELECT k, v FROM jour WHERE d=?").bind(date).all()).results;
  const o = Object.fromEntries(rows.map(r => [r.k, JSON.parse(r.v)]));
  if (!o.grille) { o.grille = makeGrid(d._ST, date); await db.prepare("INSERT OR IGNORE INTO jour (d, k, v) VALUES (?,?,?)").bind(date, "grille", JSON.stringify(o.grille)).run(); }
  if (!o.trios) { o.trios = makeTrios(d._ST, date); await db.prepare("INSERT OR IGNORE INTO jour (d, k, v) VALUES (?,?,?)").bind(date, "trios", JSON.stringify(o.trios)).run(); }
  return o;
}
const code = pid => btoa(pid.split("").reverse().join("") + "|elf").replace(/=+$/, "");
function avScore(order, ST) {
  const N = order.length, TOL = 0.049, unit = 100 / Math.floor(N * N / 2);
  const pick = order.map(([p]) => ({ p, avg: ST[p].note }));
  let F = 0;
  for (const [p, s] of order) { const a = ST[p].note; const lo = 1 + pick.filter(o => o.avg > a + TOL).length, hi = pick.filter(o => o.avg >= a - TOL).length; F += s < lo ? lo - s : s > hi ? s - hi : 0; }
  return Math.max(0, Math.round(100 - unit * F));
}
const MAXG = 8;

// ---------- classements ----------
async function names(db, devs) {
  const out = {};
  if (devs.length) {
    const { results } = await db.prepare(`SELECT dev, pseudo FROM joueurs WHERE dev IN (${devs.map(() => "?").join(",")})`).bind(...devs).all();
    for (const r of results) out[r.dev] = r.pseudo;
  }
  for (const dv of devs) if (!out[dv]) out[dv] = await autoPseudo(dv);
  return out;
}
async function board(env, d, g, k, dev) {
  const db = env.DB;
  let rows;
  if (g === "prono") {
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
  } else if (g === "col") {
    rows = (await db.prepare("SELECT dev, COUNT(*) s, COUNT(*) x FROM collection GROUP BY dev").all()).results;
  } else if (["myst", "cinq", "grille"].includes(g) && k === "saison") {
    rows = (await db.prepare("SELECT dev, SUM(s) s, COUNT(*) x FROM scores WHERE g=? GROUP BY dev").bind(g).all()).results;
  } else {
    rows = (await db.prepare("SELECT dev, s, n x FROM scores WHERE g=? AND k=?").bind(g, k).all()).results;
  }
  rows.sort((a, b) => b.s - a.s || (["myst", "cinq", "grille", "col"].includes(g) ? 0 : b.x - a.x));
  const top = rows.slice(0, 10);
  const nm = await names(db, [...new Set([...top.map(r => r.dev), dev].filter(Boolean))]);
  const i = rows.findIndex(r => r.dev === dev);
  return {
    g, k, n: rows.length,
    top: top.map((r, j) => ({ r: j + 1, p: nm[r.dev], s: Math.round(r.s * 10) / 10, x: r.x, me: r.dev === dev })),
    me: i >= 0 ? { r: i + 1, s: Math.round(rows[i].s * 10) / 10, x: rows[i].x } : null,
    pseudo: dev ? nm[dev] : null,
  };
}
async function trioStats(db, date, i, trio) {
  const own = (await db.prepare("SELECT t, r, v FROM trio_rep WHERE d=? AND i=?").bind(date, i).all()).results;
  const c = {}; for (const p of trio) c[p] = { t: 0, r: 0, v: 0 };
  for (const x of own) { if (c[x.t]) c[x.t].t++; if (c[x.r]) c[x.r].r++; if (c[x.v]) c[x.v].v++; }
  // tous les avis donnés sur ces joueurs (trios du jour et parties libres), pour les joueurs encore peu votés
  const all = {};
  for (const p of trio) {
    const q = await db.prepare("SELECT SUM(t=?1) t, SUM(r=?1) r, SUM(v=?1) v FROM trio_rep WHERE t=?1 OR r=?1 OR v=?1").bind(p).first();
    all[p] = { t: q.t || 0, r: q.r || 0, v: q.v || 0 };
  }
  return { i, n: own.length, c, all };
}

export async function onRequestOptions() { return new Response(null, { headers: H }); }
export async function onRequestGet({ request, env }) {
  if (!env.DB) return J({ error: "base non liée" }, 503);
  await init(env.DB);
  const u = new URL(request.url), q = k => u.searchParams.get(k) || "";
  const dev = DEV.test(q("dev")) ? q("dev") : null;
  const d = await data(request, env), db = env.DB, date = today();
  if (q("mystere")) {
    const pid = await mysteryOf(db, d, date);
    return J({ date, num: Math.round((Date.parse(date) - Date.parse("2026-11-08")) / 864e5) + 1, t: code(pid) });
  }
  if (q("jour")) { const o = await jour(db, d, date); return J({ date, grille: o.grille, trios: o.trios }); }
  if (q("me")) {
    if (!dev) return J({ error: "appareil" }, 400);
    const r = await db.prepare("SELECT pseudo FROM joueurs WHERE dev=?").bind(dev).first();
    return J({ pseudo: (r && r.pseudo) || await autoPseudo(dev) });
  }
  if (q("collection")) {
    if (!dev) return J({ error: "appareil" }, 400);
    const own = (await db.prepare("SELECT pid FROM collection WHERE dev=? ORDER BY ts").bind(dev).all()).results.map(r => r.pid);
    const pk = await db.prepare("SELECT v FROM packs WHERE dev=? AND d=?").bind(dev, date).first();
    return J({ pids: own, pack: !pk, packToday: pk ? JSON.parse(pk.v) : null });
  }
  if (q("trio") !== "") {
    const i = parseInt(q("trio"), 10), o = await jour(db, d, date);
    if (!(i >= 0 && i < o.trios.length)) return J({ error: "trio" }, 400);
    return J(await trioStats(db, date, i, o.trios[i]));
  }
  if (q("grille")) {
    const rows = (await db.prepare("SELECT cell, pid, COUNT(*) n FROM grille_rep WHERE d=? GROUP BY cell, pid").bind(date).all()).results;
    const tot = await db.prepare("SELECT COUNT(DISTINCT dev) n FROM grille_rep WHERE d=?").bind(date).first();
    const c = {}; for (const r of rows) (c[r.cell] = c[r.cell] || {})[r.pid] = r.n;
    return J({ n: tot.n, c });
  }
  const g = q("g");
  if (!GAMES.includes(g)) return J({ error: "jeu" }, 400);
  let k = q("k") || "saison";
  if ((g === "myst" || g === "grille") && k === "jour") k = date;
  if (g === "cinq" && k === "journee") k = String(d._last);
  return J(await board(env, d, g, k, dev));
}

export async function onRequestPost({ request, env }) {
  if (!env.DB) return J({ error: "base non liée" }, 503);
  await init(env.DB);
  let b; try { b = await request.json(); } catch (e) { return J({ error: "json" }, 400); }
  const dev = b && b.dev;
  if (!DEV.test(dev || "")) return J({ error: "appareil" }, 400);
  const ip = (await sha((request.headers.get("cf-connecting-ip") || "") + "|elf")).slice(0, 20), ts = Date.now(), db = env.DB, date = today();

  if (typeof b.pseudo === "string") {
    const p = b.pseudo.trim().replace(/\s+/g, " ");
    if (!/^[\p{L}\p{N} ._'-]{2,20}$/u.test(p)) return J({ error: "Pseudo : 2 à 20 lettres ou chiffres" }, 400);
    const taken = await db.prepare("SELECT dev FROM joueurs WHERE lower(pseudo)=lower(?) AND dev<>?").bind(p, dev).first();
    if (taken) return J({ error: "Ce pseudo est déjà pris" }, 409);
    await db.prepare("INSERT INTO joueurs (dev, pseudo, ip, ts) VALUES (?,?,?,?) ON CONFLICT(dev) DO UPDATE SET pseudo=excluded.pseudo, ts=excluded.ts").bind(dev, p, ip, ts).run();
    return J({ pseudo: p });
  }
  const d = await data(request, env), ST = d._ST;

  // ---------- collection ----------
  if (Array.isArray(b.add)) {
    const ok = [...new Set(b.add)].filter(p => ST[p] && ST[p].club).slice(0, 12);
    if (ok.length) await db.batch(ok.map(p => db.prepare("INSERT OR IGNORE INTO collection (dev, pid, src, ts) VALUES (?,?,?,?)").bind(dev, p, String(b.src || "").slice(0, 12), ts)));
    const n = await db.prepare("SELECT COUNT(*) n FROM collection WHERE dev=?").bind(dev).first();
    return J({ n: n.n });
  }
  if (b.pack) {
    const done = await db.prepare("SELECT v FROM packs WHERE dev=? AND d=?").bind(dev, date).first();
    if (done) return J({ error: "Pack déjà ouvert aujourd’hui", cards: JSON.parse(done.v) }, 409);
    const own = new Set((await db.prepare("SELECT pid FROM collection WHERE dev=?").bind(dev).all()).results.map(r => r.pid));
    const all = collectible(ST), byT = {}, TM = tierMap(ST);
    for (const p of all) (byT[TM[p]] = byT[TM[p]] || []).push(p);
    const r = rng(dev + "|" + date + "|pack"), cards = [];
    const W = [["legende", .07], ["or", .2], ["argent", .33], ["bronze", .4]];
    for (let i = 0; i < 3; i++) {
      let x = r(), t = "bronze"; for (const [id, w] of W) { if (x < w) { t = id; break; } x -= w; }
      let list = (byT[t] || []).filter(p => !own.has(p) && !cards.includes(p));
      if (!list.length) list = all.filter(p => !own.has(p) && !cards.includes(p));
      if (!list.length) list = all.filter(p => !cards.includes(p));
      const p = list[Math.floor(r() * list.length)]; cards.push(p); own.add(p);
    }
    await db.batch([
      db.prepare("INSERT INTO packs (dev, d, v) VALUES (?,?,?)").bind(dev, date, JSON.stringify(cards)),
      ...cards.map(p => db.prepare("INSERT OR IGNORE INTO collection (dev, pid, src, ts) VALUES (?,?,?,?)").bind(dev, p, "pack", ts)),
    ]);
    return J({ cards });
  }

  // ---------- titulaire · remplaçant · vendu ----------
  if (b.trio) {
    const { i, t, r, v } = b.trio, o = await jour(db, d, date);
    const trio = o.trios[i];
    if (!trio || ![t, r, v].every(p => trio.includes(p)) || new Set([t, r, v]).size !== 3) return J({ error: "trio invalide" }, 400);
    await db.prepare("INSERT OR IGNORE INTO trio_rep (d, i, dev, t, r, v, ts) VALUES (?,?,?,?,?,?,?)").bind(date, i, dev, t, r, v, ts).run();
    await db.prepare("INSERT OR IGNORE INTO collection (dev, pid, src, ts) VALUES (?,?,?,?)").bind(dev, t, "trio", ts).run();
    return J(await trioStats(db, date, i, trio));
  }

  // ---------- scores ----------
  const g = b.g;
  const many = await db.prepare("SELECT COUNT(DISTINCT dev) n FROM scores WHERE g=? AND ip=? AND dev<>? AND ts>?").bind(g, ip, dev, ts - 864e5).first();
  if (many.n >= 8) return J({ error: "trop d'appareils depuis cette connexion" }, 429);
  const best = async (k, s) => db.prepare("INSERT INTO scores (g, k, dev, s, n, ip, ts) VALUES (?,?,?,?,1,?,?) ON CONFLICT(g, k, dev) DO UPDATE SET s=MAX(s, excluded.s), n=n+1, ts=excluded.ts").bind(g, k, dev, s, ip, ts).run();
  const once = async (k, s) => db.prepare("INSERT OR IGNORE INTO scores (g, k, dev, s, n, ip, ts) VALUES (?,?,?,?,1,?,?)").bind(g, k, dev, s, ip, ts).run();
  const ok5 = p => ST[p] && ST[p].n >= 5;
  const run = Array.isArray(b.run) ? b.run.slice(0, 1000) : [];
  let extra = {};

  if (g === "pm") {
    if (!run.every(x => Array.isArray(x) && ok5(x[0]) && ok5(x[1]) && x[0] !== x[1] && ST[x[0]].note > ST[x[1]].note)) return J({ error: "série invalide" }, 400);
    await best("saison", run.length);
  } else if (g === "maillot") {
    if (!run.every(x => Array.isArray(x) && ST[x[0]] && ST[x[0]].club === x[1])) return J({ error: "série invalide" }, 400);
    await best("saison", run.length);
  } else if (g === "qui") {
    if (!run.every(p => ok5(p))) return J({ error: "série invalide" }, 400);
    await best("saison", run.length);
  } else if (g === "intrus") {
    if (!run.every(x => Array.isArray(x) && Array.isArray(x[0]) && intrusWhy(ST, x[0], x[1]))) return J({ error: "série invalide" }, 400);
    await best("saison", run.length);
  } else if (g === "av") {
    const order = Array.isArray(b.order) ? b.order : [];
    const N = order.length, mg = Math.max(1, Math.ceil(d._last / 2)), places = new Set(order.map(x => x[1]));
    if (![5, 10].includes(N) || places.size !== N || ![...places].every(s => s >= 1 && s <= N) || new Set(order.map(x => x[0])).size !== N || !order.every(x => ST[x[0]] && ST[x[0]].n >= mg)) return J({ error: "partie invalide" }, 400);
    await best("saison", avScore(order, ST));
  } else if (g === "myst") {
    const pid = await mysteryOf(db, d, date);
    const gs = Array.isArray(b.guesses) ? b.guesses.slice(0, MAXG) : [];
    if (!gs.length || !gs.every(p => ST[p])) return J({ error: "essais invalides" }, 400);
    const k = gs.indexOf(pid);
    if (!(k >= 0 || gs.length >= MAXG)) return J({ error: "partie non terminée" }, 400);
    await once(date, k >= 0 ? MAXG + 1 - (k + 1) : 0);
  } else if (g === "cinq") {
    const R = d._last, ids = new Set(d._played.filter(m => m.round === R).map(m => m.id));
    const rows = {}; for (const n of d.notes) if (ids.has(n[1]) && n[3] >= 10) rows[n[0]] = n;
    const picks = Array.isArray(b.picks) ? b.picks : [];
    const cnt = {}; for (const p of picks) if (rows[p]) cnt[rows[p][2]] = (cnt[rows[p][2]] || 0) + 1;
    if (picks.length !== 5 || new Set(picks).size !== 5 || !picks.every(p => rows[p]) || Object.values(cnt).some(c => c > 2)) return J({ error: "5 invalide" }, 400);
    await once(String(R), picks.reduce((s, p) => s + rows[p][6], 0));
  } else if (g === "grille") {
    const o = await jour(db, d, date), G = o.grille, cells = b.cells || {};
    const used = new Set(); let s = 0; const reps = [];
    for (const [cell, p] of Object.entries(cells)) {
      const [ri, ci] = cell.split("-").map(Number);
      if (!(ri >= 0 && ri < 3 && ci >= 0 && ci < 3) || used.has(p) || !gridOk(ST, p, G.clubs[ri], G.crit[ci])) return J({ error: "grille invalide" }, 400);
      used.add(p); s++; reps.push(db.prepare("INSERT OR IGNORE INTO grille_rep (d, cell, dev, pid) VALUES (?,?,?,?)").bind(date, cell, dev, p));
    }
    if (reps.length) await db.batch(reps);
    await once(date, s);
  } else return J({ error: "jeu" }, 400);

  const k = ["myst", "grille"].includes(g) ? "saison" : g === "cinq" ? String(d._last) : "saison";
  return J({ ...(await board(env, d, g, k, dev)), ...extra });
}
