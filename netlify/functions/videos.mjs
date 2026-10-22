// Dernières vidéos de la chaîne YouTube EuroLeague France (flux RSS public, 15 plus récentes)
const CHANNEL = "UCxJxcIcu86bXIzBdO9-UnqQ";
const dec = s => s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
export default async () => {
  try {
    const r = await fetch(`https://www.youtube.com/feeds/videos.xml?channel_id=${CHANNEL}`);
    if (!r.ok) throw new Error(String(r.status));
    const x = await r.text();
    const videos = [...x.matchAll(/<entry>([\s\S]*?)<\/entry>/g)].map(([, e]) => ({
      id: (e.match(/<yt:videoId>([^<]+)/) || [])[1],
      title: dec((e.match(/<title>([^<]*)/) || [])[1] || ""),
      date: ((e.match(/<published>([^<]+)/) || [])[1] || "").slice(0, 19),
    })).filter(v => v.id);
    return new Response(JSON.stringify({ videos }), {
      headers: { "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=600", "access-control-allow-origin": "*" },
    });
  } catch (e) {
    return new Response(JSON.stringify({ videos: [], error: String(e) }), { status: 200, headers: { "content-type": "application/json" } });
  }
};
export const config = { path: "/api/videos" };
