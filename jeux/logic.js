// Logique commune des jeux EuroLeague France : utilisée par la page (jeux/index.html) ET par le serveur (functions/api/scores.js),
// pour que la grille du jour, les trios et l'intrus soient vérifiés exactement comme ils sont générés.

export const EUROPE = new Set(["ESP","SRB","GER","ITA","LTU","GRE","TUR","FIN","LAT","CRO","SLO","DEN","MKD","GEO","CZE","POL","BUL","HUN","SVK","SWE","IRL","UK","UKR","BIH","MNE","ARM","BEL","NED","AUT","POR","ISR"]);
export const POS = { G: "Arrière", F: "Ailier", C: "Pivot" };

// statistiques de saison (sans nos notes pour ce qui sert aux critères : points, éval, minutes, poste, nationalité)
export function buildST(d) {
  const ST = {};
  for (const [p, m, c, min, ev, pm, note] of d.notes) {
    const s = ST[p] || (ST[p] = { n: 0, note: 0, ev: 0, min: 0 });
    s.n++; s.note += note; s.ev += ev; s.min += min;
  }
  const photos = new Set(d.photos || []);
  for (const p in ST) {
    const s = ST[p];
    s.note /= s.n; s.ev /= s.n; s.min /= s.n;
    s.club = d.players[p] ? d.players[p].club : null;
    const fp = (d.fantasy && d.fantasy.p && d.fantasy.p[p]) || [];
    s.pos = fp[0] || null; s.price = fp[1] || 0;
    s.nat = (d.nat || {})[p] || null;
    const pts = d.pts && d.pts[p] ? Object.values(d.pts[p]) : [];
    s.ppg = pts.length >= Math.max(1, Math.floor(s.n * 0.8)) ? pts.reduce((a, b) => a + b, 0) / pts.length : null;
    s.photo = photos.has(p);
  }
  return ST;
}

// générateur pseudo-aléatoire reproductible (même graine = même tirage partout)
export function rng(seed) {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) { h = Math.imul(h ^ seed.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
  let a = h >>> 0;
  return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
export const shuffleR = (a, r) => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

/* ---------- LA GRILLE 3 × 3 (sans nos notes) ---------- */
export const CRIT = [
  { id: "fra", t: "nat", lab: "Français", f: s => s.nat === "FRA" },
  { id: "usa", t: "nat", lab: "Américain", f: s => s.nat === "USA" },
  { id: "eur", t: "nat", lab: "Européen (hors France)", f: s => !!s.nat && s.nat !== "FRA" && EUROPE.has(s.nat) },
  { id: "g", t: "pos", lab: "Arrière / meneur", f: s => s.pos === "G" },
  { id: "f", t: "pos", lab: "Ailier", f: s => s.pos === "F" },
  { id: "c", t: "pos", lab: "Pivot", f: s => s.pos === "C" },
  { id: "p10", t: "pts", lab: "10 pts ou + par match", f: s => s.ppg != null && s.ppg >= 10 },
  { id: "p6", t: "pts", lab: "Moins de 6 pts par match", f: s => s.ppg != null && s.ppg < 6 },
  { id: "e10", t: "ev", lab: "10 d’éval ou + par match", f: s => s.ev >= 10 },
  { id: "m25", t: "min", lab: "25 min ou + par match", f: s => s.min >= 25 },
  { id: "m15", t: "min", lab: "Moins de 15 min par match", f: s => s.min < 15 },
];
export const critOf = id => CRIT.find(c => c.id === id);
export const gridOk = (ST, pid, club, crit) => { const s = ST[pid], c = critOf(crit); return !!(s && c && s.n >= 2 && s.club === club && c.f(s)); };
export function makeGrid(ST, date) {
  const r = rng("elf-grille-" + date);
  const clubs = [...new Set(Object.values(ST).map(s => s.club).filter(Boolean))].sort();
  for (let tries = 0; tries < 400; tries++) {
    const cs = shuffleR(clubs, r).slice(0, 3);
    const types = new Set(); const cr = [];
    for (const c of shuffleR(CRIT, r)) { if (types.has(c.t)) continue; types.add(c.t); cr.push(c.id); if (cr.length === 3) break; }
    const ok = cs.every(club => cr.every(k => Object.keys(ST).filter(p => gridOk(ST, p, club, k)).length >= 2));
    if (ok) return { clubs: cs, crit: cr };
  }
  return null;
}

/* ---------- TITULAIRE · REMPLAÇANT · VENDU ---------- */
export const starPool = ST => Object.keys(ST).filter(p => ST[p].n >= 3 && ST[p].photo && ST[p].price).sort((a, b) => ST[b].price - ST[a].price || (a < b ? -1 : 1)).slice(0, 45);
export function makeTrios(ST, date, n = 5) {
  const r = rng("elf-trio-" + date), pool = shuffleR(starPool(ST), r), out = [];
  for (let i = 0; i + 3 <= pool.length && out.length < n; i += 3) out.push(pool.slice(i, i + 3));
  return out;
}

/* ---------- L'INTRUS ---------- */
// propriétés comparées : club, nationalité, poste, niveau de points
const tierPts = s => s.ppg == null ? null : s.ppg >= 12 ? "12+" : "-12";
export const PROPS = [["club", s => s.club], ["nat", s => s.nat], ["pos", s => s.pos], ["pts", tierPts]];
// renvoie la propriété partagée par les 3 autres et pas par l'intrus, si l'intrus est le SEUL possible ; sinon null
export function intrusWhy(ST, four, intruder) {
  if (four.length !== 4 || new Set(four).size !== 4 || !four.includes(intruder) || !four.every(p => ST[p])) return null;
  const why = c => { const o = four.filter(x => x !== c); for (const [k, f] of PROPS) { const v = f(ST[o[0]]); if (v != null && o.every(x => f(ST[x]) === v) && f(ST[c]) !== v) return [k, v]; } return null; };
  const cand = four.filter(c => why(c));
  return cand.length === 1 && cand[0] === intruder ? why(intruder) : null;
}
export function makeIntrus(ST, rand = Math.random) {
  const pool = Object.keys(ST).filter(p => ST[p].n >= 3 && ST[p].photo && ST[p].club && ST[p].nat && ST[p].pos);
  for (let t = 0; t < 300; t++) {
    const [k, f] = PROPS[Math.floor(rand() * PROPS.length)];
    const groups = {};
    for (const p of pool) { const v = f(ST[p]); if (v != null) (groups[v] = groups[v] || []).push(p); }
    const vals = Object.keys(groups).filter(v => groups[v].length >= 3);
    if (!vals.length) continue;
    const v = vals[Math.floor(rand() * vals.length)];
    const g = shuffleR(groups[v], rand).slice(0, 3);
    const out = pool.filter(p => f(ST[p]) !== v && f(ST[p]) != null);
    const intr = out[Math.floor(rand() * out.length)];
    const four = shuffleR([...g, intr], rand);
    if (intrusWhy(ST, four, intr)) return { four, intruder: intr };
  }
  return null;
}

/* ---------- COLLECTION ---------- */
export const TIERS = { legende: "Légende", or: "Or", argent: "Argent", bronze: "Bronze" };
// rareté selon le rang de la moyenne de notes (joueurs avec 3 matchs ou plus) : 6 % Légende, 16 % Or, 33 % Argent, le reste Bronze
export function tierMap(ST) {
  const el = Object.keys(ST).filter(p => ST[p].n >= 3).sort((a, b) => ST[b].note - ST[a].note || (a < b ? -1 : 1));
  const m = {}, N = el.length;
  el.forEach((p, i) => { const q = i / N; m[p] = q < 0.06 ? "legende" : q < 0.22 ? "or" : q < 0.55 ? "argent" : "bronze"; });
  for (const p in ST) if (!m[p]) m[p] = "bronze";
  return m;
}
export const collectible = ST => Object.keys(ST).filter(p => ST[p].club).sort((a, b) => (ST[a].club < ST[b].club ? -1 : ST[a].club > ST[b].club ? 1 : (a < b ? -1 : 1)));
