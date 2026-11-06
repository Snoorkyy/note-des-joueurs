"""Posts X « en un geste » : visuel du match, page de partage (carte X), texte du tweet, notification ntfy.

  python3 robot/share.py rebuild 99[,100]  -> remet en file d'attente des matchs déjà publiés (re-lit l'API)
  python3 robot/share.py render            -> fabrique og/m/<id>.png et m/<id>.html pour la file d'attente
  python3 robot/share.py notify            -> attend que la carte soit en ligne puis envoie les notifications ntfy
  python3 robot/share.py instagram         -> publie la story Instagram de chaque match (og/m/<id>-story.jpg), secret IG_TOKEN
La file d'attente est robot/share_queue.json (non versionnée)."""
import json, os, sys, time, hashlib, unicodedata, urllib.request, urllib.parse, datetime as dt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "robot", "share_queue.json")
SITE = "https://note-des-joueurs.pages.dev"
NOTES = "https://www.euroleague-france.com/notes-des-joueurs/"

# Noms de clubs en français, avec l'article qui va bien dans une phrase
FRN = {'ASV': "l'ASVEL", 'BAR': "le Barça", 'BAS': "Baskonia", 'BES': "le Besiktas", 'DUB': "Dubaï", 'HTA': "l'Hapoel Tel-Aviv",
       'IST': "l'Efes", 'MAD': "le Real Madrid", 'MIL': "Milan", 'MUN': "le Bayern", 'OLY': "l'Olympiacos", 'PAM': "Valence",
       'PAN': "le Panathinaïkos", 'PAR': "le Partizan", 'PRS': "Paris", 'RED': "l'Étoile Rouge", 'TEL': "le Maccabi",
       'ULK': "Fenerbahçe", 'VIR': "la Virtus", 'ZAL': "le Žalgiris"}
CARD = {'ASV': "ASVEL", 'BAR': "Barcelone", 'BAS': "Baskonia", 'BES': "Besiktas", 'DUB': "Dubaï", 'HTA': "Hapoel Tel-Aviv",
        'IST': "Anadolu Efes", 'MAD': "Real Madrid", 'MIL': "Milan", 'MUN': "Bayern Munich", 'OLY': "Olympiacos", 'PAM': "Valence",
        'PAN': "Panathinaïkos", 'PAR': "Partizan", 'PRS': "Paris", 'RED': "Étoile Rouge", 'TEL': "Maccabi Tel-Aviv",
        'ULK': "Fenerbahçe", 'VIR': "Virtus Bologne", 'ZAL': "Žalgiris"}
MOIS = "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split()

def cap(s): return s[:1].upper() + s[1:]
def nfr(x): return (f"{x:.1f}".replace(".0", "").replace(".", ","))
def pname(d, pid):
    n = d["players"][pid]["name"]
    last, _, first = n.partition(",")
    full = f"{first.strip()} {last.strip()}".strip()
    for a, b in ((" Iv", " IV"), (" Iii", " III"), (" Ii", " II"), (" Jr", " Jr.")):
        if full.endswith(a): full = full[: -len(a)] + b
    return full.replace("Jr..", "Jr.")

def wlen(t):
    """Longueur comptée par X : URL = 23, caractères hors latin/ponctuation = 2."""
    n = 0
    for w in t.split(" "):
        pass
    import re
    t2 = re.sub(r"https?://\S+", "x" * 23, t)
    for ch in t2:
        o = ord(ch)
        n += 1 if (o <= 0x10FF or 0x2000 <= o <= 0x200D or 0x2010 <= o <= 0x201F or 0x2032 <= o <= 0x2037) else 2
    return n

def stats_line(r):
    reb = r["orb"] + r["drb"]
    parts = [f"{r['pts']} pts"]
    if r["m3"] >= 4 and r["m3"] / max(1, r["a3"]) >= .5: parts.append(f"{r['m3']}/{r['a3']} à 3 pts")
    extra = [(reb, 5, f"{reb} rbds"), (r["ast"], 4, f"{r['ast']} pd"), (r["stl"], 3, f"{r['stl']} int"), (r["blk"], 2, f"{r['blk']} ctr")]
    extra = [e for e in extra if e[0] >= e[1]]
    extra.sort(key=lambda e: -(e[0] / e[1]))
    parts += [e[2] for e in extra[:3 - len(parts)]]
    parts.append(f"{r['pir']} d'éval")
    return " · ".join(parts)

def build(d, g, box, rows):
    mid = f"E2026-{g['code']}"
    notes = {r[0]: r[6] for r in rows}
    hs, as_ = g["score"]; home, away = g["A"], g["B"]
    W, L = (home, away) if hs > as_ else (away, home)
    ws, ls = max(hs, as_), min(hs, as_); mg = ws - ls
    ot = "#5" in g["pbp"].split()
    played = [p for p in notes if p in box]
    def key(p): return (notes[p], box[p]["pir"])
    mvp = max(played, key=key)
    pool = [p for p in played if box[p]["min"] >= 15] or played
    flop = min(pool, key=key)
    if notes[flop] > 4.5 or flop == mvp: flop = None
    frs = set(d.get("fr", [])) | {p for p, c in d.get("nat", {}).items() if c == "FRA"}
    french = sorted([p for p in played if p in frs and box[p]["min"] >= 8], key=lambda p: -notes[p])[:3]
    h = int(hashlib.md5(mid.encode()).hexdigest(), 16)
    pick = lambda xs: xs[h % len(xs)]
    w, l = FRN[W], FRN[L]
    if ot: head, emo = f"{cap(w)} s'impose après prolongation contre {l}", " 🔥"
    elif mg <= 3: head, emo = pick([f"{cap(w)} arrache la victoire contre {l}", f"{cap(w)} fait plier {l} au finish", f"{cap(w)} s'en sort au buzzer contre {l}"]), " 🔥"
    elif mg <= 9: head, emo = pick([f"{cap(w)} bat {l}", f"{cap(w)} prend le meilleur sur {l}", f"{cap(w)} s'impose contre {l}"]), ""
    elif mg <= 19: head, emo = pick([f"{cap(w)} domine {l}", f"{cap(w)} s'impose nettement contre {l}", f"{cap(w)} maîtrise {l}"]), ""
    else: head, emo = pick([f"{cap(w)} écrase {l}", f"{cap(w)} corrige {l}", f"{cap(w)} atomise {l}"]), " 💥"
    url = f"{SITE}/m/{mid}"
    rnd = g["round"]
    L_head = f"{head} ({ws}-{ls}){emo}"
    L_mvp = f"⭐ {pname(d, mvp)} {nfr(notes[mvp])}/10 ({stats_line(box[mvp])})"
    L_mvp_short = f"⭐ {pname(d, mvp)} {nfr(notes[mvp])}/10"
    L_flop = f"📉 {pname(d, flop)} {nfr(notes[flop])}/10" if flop else None
    L_fr = ("🇫🇷 " + " · ".join(f"{pname(d, p)} {nfr(notes[p])}" for p in french)) if french else None
    L_end = f"Et toi, tu leur mets combien ? 👉 {url}\n\n#EuroLeague"
    def compose(mv, fl, fr_):
        body = [L_head, "", mv] + ([fl] if fl else []) + ([fr_] if fr_ else []) + ["", L_end]
        return "\n".join(body)
    for args in ((L_mvp, L_flop, L_fr), (L_mvp_short, L_flop, L_fr), (L_mvp_short, L_flop, None), (L_mvp_short, None, None)):
        text = compose(*args)
        if wlen(text) <= 280: break
    assert text.rstrip().endswith("#EuroLeague") and wlen(text) <= 280, text
    y, m, dd = g["date"].split("-")
    tags = []
    if ot: tags.append("Après prolongation")
    elif mg <= 3: tags.append("Au finish")
    elif mg >= 20: tags.append("Démonstration")
    if W == away: tags.append("Victoire à l'extérieur")
    photos = set(d.get("photos", []))
    rest = sorted([p for p in played if p not in (mvp, flop)], key=lambda p: (-(p in french), -notes[p], -box[p]["pir"]))
    top = sorted(rest[:4], key=lambda p: (-notes[p], -box[p]["pir"]))
    P = lambda p: {"id": p, "n": pname(d, p), "note": notes[p], "photo": p in photos}
    card = {"kicker": f"Journée {rnd} · {int(dd)} {MOIS[int(m) - 1]}", "home": home, "away": away, "hn": CARD[home], "an": CARD[away],
            "hs": hs, "as": as_, "tag": " · ".join(tags),
            "mvp": {**P(mvp), "st": stats_line(box[mvp])}, "flop": P(flop) if flop else None,
            "top": [{**P(p), "fra": p in frs} for p in top]}
    # story Instagram : jusqu'à 7 autres joueurs (Français assurés d'y figurer), classés par note
    oth = [p for p in played if p not in (mvp, flop) and box[p]["min"] >= 10]
    keep = [p for p in oth if p in frs][:3]
    keep += [p for p in sorted(oth, key=lambda p: (-notes[p], -box[p]["pir"])) if p not in keep][:7 - len(keep)]
    card["lst"] = [{**P(p), "fra": p in frs, "club": d["players"][p]["club"]}
                   for p in sorted(keep, key=lambda p: (-notes[p], -box[p]["pir"]))]
    if card["flop"]: card["flop"]["club"] = d["players"][flop]["club"]
    card["mvp"]["club"] = d["players"][mvp]["club"]
    title = f"{CARD[home]} {hs}-{as_} {CARD[away]} · Les notes /10"
    desc = f"MVP : {pname(d, mvp)} {nfr(notes[mvp])}/10. Toutes les notes du match… et à toi de noter les joueurs !"
    return {"id": mid, "round": rnd, "card": card, "tweet": text, "url": url, "title": title, "desc": desc,
            "notif": f"{CARD[home]} {hs}-{as_} {CARD[away]} : post prêt"}

def queue_add(items):
    q = json.load(open(QUEUE)) if os.path.exists(QUEUE) else []
    ids = {i["id"] for i in items}
    q = [i for i in q if i["id"] not in ids] + items
    json.dump(q, open(QUEUE, "w"), ensure_ascii=False, indent=1)

PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:type" content="article"><meta property="og:site_name" content="EuroLeague France">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}"><meta property="og:image" content="{img}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}"><meta name="twitter:image" content="{img}">
<meta http-equiv="refresh" content="0; url={dest}"><link rel="canonical" href="{dest}">
</head><body style="background:#060D24;color:#fff;font-family:sans-serif;text-align:center;padding:40px">
<p><a style="color:#FFB547" href="{dest}">Noter les joueurs du match</a></p>
<script>location.replace({dest_js})</script></body></html>
"""

def render():
    from playwright.sync_api import sync_playwright
    q = json.load(open(QUEUE)) if os.path.exists(QUEUE) else []
    if not q: print("rien à fabriquer"); return
    os.makedirs(os.path.join(ROOT, "og", "m"), exist_ok=True); os.makedirs(os.path.join(ROOT, "m"), exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 630})
        pg.goto("file://" + os.path.join(ROOT, "robot", "share", "card.html"))
        sp = b.new_page(viewport={"width": 1080, "height": 1920})
        sp.goto("file://" + os.path.join(ROOT, "robot", "share", "story.html"))
        for it in q:
            pg.evaluate("D=>window.render(D)", it["card"]); pg.wait_for_timeout(300)
            png = os.path.join(ROOT, "og", "m", it["id"] + ".png")
            pg.screenshot(path=png)
            try:
                sp.evaluate("D=>window.render(D)", it["card"]); sp.wait_for_timeout(300)
                sp.screenshot(path=os.path.join(ROOT, "og", "m", it["id"] + "-story.jpg"), type="jpeg", quality=90)
            except Exception as e: print("::warning::story non fabriquée", it["id"], e)
            dest = f"{SITE}/vote.html?m={it['id']}"
            esc = lambda s: s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
            html = PAGE.format(title=esc(it["title"]), desc=esc(it["desc"]), url=it["url"], img=f"{SITE}/og/m/{it['id']}.png",
                               dest=dest, dest_js=json.dumps(dest))
            open(os.path.join(ROOT, "m", it["id"] + ".html"), "w", encoding="utf-8").write(html)
            print("fabriqué", it["id"], "| tweet", wlen(it["tweet"]), "car.")
        b.close()

def notify(dry=False):
    topic = os.environ.get("NTFY_TOPIC")
    q = json.load(open(QUEUE)) if os.path.exists(QUEUE) else []
    if not q: print("aucune notification"); return
    if not topic and not dry: print("::warning::NTFY_TOPIC absent : notifications non envoyées"); return
    for it in q:
        img = f"{SITE}/og/m/{it['id']}.png"
        for _ in range(30):                     # attendre la mise en ligne Cloudflare (carte X)
            try:
                with urllib.request.urlopen(urllib.request.Request(f"{SITE}/m/{it['id']}", headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
                    ok = r.status == 200 and it["id"] in r.read().decode()
                with urllib.request.urlopen(urllib.request.Request(img + "?v=" + str(time.time()), headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
                    ok = ok and r.status == 200
                if ok: break
            except Exception: pass
            time.sleep(10)
        intent = "https://x.com/intent/post?text=" + urllib.parse.quote(it["tweet"])
        msg = {"topic": topic, "title": it["notif"], "message": it["tweet"], "click": intent, "attach": img,
               "tags": ["basketball"], "actions": [{"action": "view", "label": "Publier sur X", "url": intent, "clear": True}]}
        if dry: print(json.dumps(msg, ensure_ascii=False, indent=1)); continue
        req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r: print("notifié", it["id"], r.status)

GRAPH = "https://graph.facebook.com/v24.0"
def _graph(path, data=None):
    url = f"{GRAPH}/{path}"
    tok = os.environ["IG_TOKEN"]
    if data is None:
        url += ("&" if "?" in url else "?") + "access_token=" + urllib.parse.quote(tok); req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode({**data, "access_token": tok}).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(e.read().decode()[:400])

def instagram():
    """Publie en story Instagram le visuel 1080x1920 de chaque match de la file (API Graph de Meta, gratuite).
    Secret IG_TOKEN = jeton d'accès de la page Facebook liée au compte Instagram professionnel (n'expire pas)."""
    if not os.environ.get("IG_TOKEN"): print("::warning::IG_TOKEN absent : stories Instagram non publiées"); return 0
    q = json.load(open(QUEUE)) if os.path.exists(QUEUE) else []
    if not q: print("aucune story"); return 0
    ig = os.environ.get("IG_USER_ID") or _graph("me?fields=instagram_business_account")["instagram_business_account"]["id"]
    bad = 0
    for it in q:
        img = f"{SITE}/og/m/{it['id']}-story.jpg"
        for _ in range(30):
            try:
                with urllib.request.urlopen(urllib.request.Request(img + "?v=" + str(time.time()), headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
                    if r.status == 200: break
            except Exception: pass
            time.sleep(10)
        try:
            c = _graph(f"{ig}/media", {"image_url": img, "media_type": "STORIES"})["id"]
            for _ in range(30):
                st = _graph(f"{c}?fields=status_code").get("status_code")
                if st == "FINISHED": break
                if st == "ERROR": raise RuntimeError("traitement de l'image refusé par Instagram")
                time.sleep(4)
            r = _graph(f"{ig}/media_publish", {"creation_id": c})
            print("story Instagram publiée", it["id"], r.get("id"))
        except Exception as e:
            bad += 1; print("::error::story Instagram non publiée pour", it["id"], ":", e)
    return 1 if bad else 0

def rebuild(codes):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import run
    d = json.load(open(os.path.join(ROOT, "data.json"), encoding="utf-8"))
    items = []
    for c in codes:
        g = run.extract(c); rows, err, box = run.rate(g)
        items.append(build(d, g, box, rows))
    queue_add(items)
    for it in items: print(it["tweet"], "\n---", wlen(it["tweet"]))

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "render": render()
    elif a[0] == "notify": notify(dry="--dry" in a)
    elif a[0] == "instagram": sys.exit(instagram())
    elif a[0] == "rebuild": rebuild([int(x) for x in a[1].split(",")])
