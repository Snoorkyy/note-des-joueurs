// Cloudflare Pages Function — POST /api/share : enregistre le visuel « Mes notes » d'un lecteur (JPEG fabriqué dans son navigateur).
// Corps : {m, dev, img: "data:image/jpeg;base64,..."} -> {id}. Un visuel par appareil et par match (remplacé s'il recommence).
// L'image est ensuite servie par /s/<id>.jpg et la page de partage /s/<id> (carte X).
const H = { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*", "access-control-allow-headers": "content-type" };
const J = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: H });
export async function onRequestOptions() { return new Response(null, { headers: H }); }
export async function onRequestPost({ request, env }) {
  if (!env.DB) return J({ error: "base non liée" }, 503);
  let b; try { b = await request.json(); } catch (e) { return J({ error: "json" }, 400); }
  const { m, dev, img } = b || {};
  if (!/^E\d{4}-\d{1,3}$/.test(m || "") || !/^[A-Za-z0-9-]{16,64}$/.test(dev || "") || typeof img !== "string" || !img.startsWith("data:image/jpeg;base64,")) return J({ error: "requête" }, 400);
  const raw = Uint8Array.from(atob(img.slice(23)), c => c.charCodeAt(0));
  if (raw.length > 450000 || raw[0] !== 0xFF || raw[1] !== 0xD8) return J({ error: "image" }, 400);
  await env.DB.prepare("CREATE TABLE IF NOT EXISTS shares (id TEXT PRIMARY KEY, m TEXT NOT NULL, dev TEXT NOT NULL, img BLOB NOT NULL, ts INTEGER, UNIQUE (m, dev))").run();
  // seul un lecteur qui a voté sur ce match peut publier son visuel
  const v = await env.DB.prepare("SELECT COUNT(*) n FROM votes WHERE m=? AND dev=?").bind(m, dev).first();
  if (!v || !v.n) return J({ error: "vote d'abord" }, 403);
  const old = await env.DB.prepare("SELECT id FROM shares WHERE m=? AND dev=?").bind(m, dev).first();
  const id = old ? old.id : [...crypto.getRandomValues(new Uint8Array(6))].map(x => x.toString(36).padStart(2, "0")).join("").slice(0, 10);
  await env.DB.prepare("INSERT OR REPLACE INTO shares (id, m, dev, img, ts) VALUES (?,?,?,?,?)").bind(id, m, dev, raw, Date.now()).run();
  return J({ id });
}
