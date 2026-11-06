"""Lettre d'info hebdomadaire EuroLeague France (fabriquée le samedi matin à partir de data.json).

  python3 robot/newsletter.py build [--date 2026-11-07]  -> newsletter/<date>.html (version e-mail = version web)
                                                          + og/nl/<date>-cinq.jpg (visuel « Le cinq de la semaine »)
                                                          + robot/newsletter_meta.json (objet, pré-en-tête)
  python3 robot/newsletter.py draft                      -> crée le brouillon dans Kit (secret KIT_API_KEY), sans l'envoyer
Toutes les données viennent de data.json ; votes des lecteurs et vidéo YouTube lus sur le site (facultatifs)."""
import json, os, sys, datetime as dt, urllib.request, urllib.parse, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import share
ROOT = share.ROOT; SITE = share.SITE; NOTES = share.NOTES
MOIS = share.MOIS
E = html.escape
NC = lambda n: "#17633A" if n >= 8.5 else "#2E8048" if n >= 7 else "#6F7F3F" if n >= 5.5 else "#B08816" if n >= 4.5 else "#C4521E" if n >= 3 else "#A01E16"
nfr = share.nfr
def dfr(s, year=False):
    y, m, d = map(int, s.split("-")); return f"{'1er' if d == 1 else d} {MOIS[m-1]}" + (f" {y}" if year else "")
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r: return json.loads(r.read().decode())
    except Exception as e:
        print("::warning::lecture impossible", url, e); return None

def collect(day):
    d = json.load(open(os.path.join(ROOT, "data.json"), encoding="utf-8"))
    end = dt.date.fromisoformat(day); start = end - dt.timedelta(days=6)
    ms = [m for m in d["matches"] if start.isoformat() <= m["date"] <= end.isoformat()]
    if not ms: return d, None
    ids = {m["id"] for m in ms}; by = {m["id"]: m for m in ms}
    N = [n for n in d["notes"] if n[1] in ids]
    frs = set(d.get("fr", [])) | {p for p, c in d.get("nat", {}).items() if c == "FRA"}
    ph = set(d.get("photos", []))
    rounds = sorted({m["round"] for m in ms})
    start, end = dt.date.fromisoformat(min(m["date"] for m in ms)), dt.date.fromisoformat(max(m["date"] for m in ms))
    return d, dict(ms=sorted(ms, key=lambda m: (m["date"], int(m["id"].split("-")[1]))), N=N, by=by, frs=frs, ph=ph, rounds=rounds, start=start, end=end)

def opp(W, n):
    m = W["by"][n[1]]; return m["away"] if m["home"] == n[2] else m["home"]

def build(day):
    d, W = collect(day)
    if not W: print("aucun match cette semaine : pas de lettre"); return None
    pn = lambda p: share.pname(d, p)
    club = lambda c: share.CARD.get(c, d["clubs"][c]["name"])
    N = W["N"]; rtxt = "Journée " + " et ".join(str(r) for r in W["rounds"]) if len(W["rounds"]) > 1 else f"Journée {W['rounds'][0]}"
    rshort = "J" + "-J".join(str(r) for r in W["rounds"])
    # le cinq : meilleure note de chaque joueur sur la semaine, ≥ 15 min
    best = {}
    for n in N:
        if n[3] >= 15 and (n[0] not in best or (n[6], n[4]) > (best[n[0]][6], best[n[0]][4])): best[n[0]] = n
    five = sorted(best.values(), key=lambda n: (-n[6], -n[4]))[:5]
    mvp = five[0]
    flop = min([n for n in N if n[3] >= 20], key=lambda n: (n[6], n[4]))
    fr_rows = sorted([n for n in N if n[0] in W["frs"] and n[3] >= 5], key=lambda n: -n[6])
    # visuel
    card = {"kicker": f"{rtxt} · {span(W)}".upper(),
            "five": [{"id": n[0], "n": pn(n[0]), "note": n[6], "photo": n[0] in W["ph"], "club": n[2], "fra": n[0] in W["frs"],
                      "mt": f"{Math.r(n[3])} min · {n[4]} d'éval · vs {club(opp(W, n))}"} for n in five]}
    # votes des lecteurs (écarts avec nos notes, ≥ 5 votes)
    va = (get(SITE + "/api/vote") or {}).get("a", {})
    gaps = []
    for n in N:
        r = va.get(n[1], {}).get(n[0])
        if r and r[1] >= 5 and abs(r[0] - n[6]) >= 1: gaps.append((abs(r[0] - n[6]), n, r))
    gaps = sorted(gaps, key=lambda z: -z[0])[:3]
    nvotes = sum(r[1] for m in va.values() for r in m.values() if True) if va else 0
    # fantasy : prochaine journée, blessés notables
    nxt = min([f[0] for f in d.get("fixtures", []) if f[1] > W["end"].isoformat()] or [0])
    fx = [f for f in d.get("fixtures", []) if f[0] == nxt]
    fp = d.get("fantasy", {}).get("p", {})
    inj = [x for x in d.get("news", {}).get("list", []) if x.get("s") in ("out", "doubt") and x.get("p") and fp.get(x["p"], [0, 0])[1] >= 11]
    inj = sorted(inj, key=lambda x: (x["s"] != "out", -fp[x["p"]][1]))[:8]
    vid = ((get(SITE + "/api/videos") or {}).get("videos") or [None])[0]
    std = d.get("standings", {}).get("rows", [])[:8]
    return dict(d=d, W=W, rtxt=rtxt, rshort=rshort, five=five, mvp=mvp, flop=flop, fr_rows=fr_rows, card=card, gaps=gaps, nxt=nxt, fx=fx,
                inj=inj, vid=vid, std=std, pn=pn, club=club, nvotes=nvotes)

class Math:
    @staticmethod
    def r(x): return int(round(x))

def chip(n, size=16):
    return (f'<span style="display:inline-block;min-width:40px;padding:5px 8px;border-radius:8px;background:{NC(n)};color:#fff;'
            f'font:800 {size}px Arial,Helvetica,sans-serif;text-align:center">{nfr(round(n * 2) / 2)}</span>')

def h2(t, sub=""):
    return (f'<tr><td style="padding:30px 28px 10px"><div style="font:800 13px Arial,Helvetica,sans-serif;letter-spacing:2px;color:#ED2939;text-transform:uppercase">{sub}</div>'
            f'<div style="font:800 24px Arial,Helvetica,sans-serif;color:#0B1638;text-transform:uppercase;margin-top:2px">{t}</div></td></tr>')

def html_email(B, day):
    d, W, pn, club = B["d"], B["W"], B["pn"], B["club"]
    img = f"{SITE}/og/nl/{day}-cinq.jpg"
    vote = f"{SITE}/vote.html"
    notes = f"{NOTES}#journee-{W['rounds'][-1]}"
    T = []
    a = T.append
    pre = f"{pn(B['mvp'][0])} {nfr(B['mvp'][6])}/10, le cinq de la semaine, les Français et la fantasy de la {B['rshort']}."
    a(f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>La lettre EuroLeague France · {B['rshort']}</title></head>
<body style="margin:0;padding:0;background:#EEF1F8">
<div style="display:none;max-height:0;overflow:hidden">{E(pre)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF1F8"><tr><td align="center" style="padding:20px 10px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden">
<tr><td style="background:#060D24;padding:26px 28px 22px" align="left">
 <a href="{NOTES}"><img src="{SITE}/logo_white.png" alt="EuroLeague France" height="44" style="display:block;height:44px;border:0"></a>
 <div style="font:800 13px Arial,Helvetica,sans-serif;letter-spacing:3px;color:#FFB547;margin-top:18px">LA LETTRE DU SAMEDI · {E(B['rtxt'].upper())}</div>
 <div style="font:800 30px/1.1 Arial,Helvetica,sans-serif;color:#ffffff;margin-top:6px">{E(pn(B['mvp'][0]))} règne sur la semaine</div>
 <div style="font:15px/1.5 Arial,Helvetica,sans-serif;color:#AEB9E0;margin-top:8px">{len(W['ms'])} matchs et {len(W['N'])} joueurs notés {span(W)}. Voici ce qu'il fallait retenir.</div>
</td></tr>
<tr><td style="height:6px;background:linear-gradient(90deg,#002395 0 33%,#fff 33% 66%,#ED2939 66%);background-color:#002395"></td></tr>
<tr><td style="padding:0"><a href="{notes}"><img src="{img}" width="600" alt="Le cinq de la semaine" style="display:block;width:100%;height:auto;border:0"></a></td></tr>''')
    # MVP / flop
    m, f = B["mvp"], B["flop"]
    a(h2("MVP et flop de la semaine", "Les extrêmes"))
    a(f'''<tr><td style="padding:0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td style="padding:12px 14px;background:#F4F7FD;border-radius:12px;font:15px/1.45 Arial,Helvetica,sans-serif;color:#1B2440">⭐ <b>{E(pn(m[0]))}</b> ({E(club(m[2]))}) {chip(m[6])}<br><span style="color:#5B6584">{Math.r(m[3])} min · {m[4]} d'évaluation face à {E(club(opp(W, m)))}</span></td></tr>
<tr><td style="height:8px"></td></tr>
<tr><td style="padding:12px 14px;background:#FFF4F4;border-radius:12px;font:15px/1.45 Arial,Helvetica,sans-serif;color:#1B2440">📉 <b>{E(pn(f[0]))}</b> ({E(club(f[2]))}) {chip(f[6])}<br><span style="color:#5B6584">{Math.r(f[3])} min · {f[4]} d'évaluation face à {E(club(opp(W, f)))}</span></td></tr>
</table></td></tr>''')
    # Français
    if B["fr_rows"]:
        a(h2("Les Français", "🇫🇷 Nos joueurs"))
        rows = "".join(f'<tr><td style="padding:8px 0;border-bottom:1px solid #E8ECF5;font:15px Arial,Helvetica,sans-serif;color:#1B2440"><b>{E(pn(n[0]))}</b> <span style="color:#7A84A3">· {E(club(n[2]))} vs {E(club(opp(W, n)))} · {Math.r(n[3])} min</span></td><td align="right" style="padding:8px 0;border-bottom:1px solid #E8ECF5">{chip(n[6], 15)}</td></tr>' for n in B["fr_rows"][:12])
        a(f'<tr><td style="padding:0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table></td></tr>')
    # résultats
    a(h2("Les résultats", "À toi de noter"))
    rows = ""
    for g in W["ms"]:
        hw = g["hs"] > g["as"]
        rows += (f'<tr><td style="padding:9px 0;border-bottom:1px solid #E8ECF5;font:15px Arial,Helvetica,sans-serif;color:#1B2440">'
                 f'<span style="{"font-weight:800" if hw else "color:#7A84A3"}">{E(club(g["home"]))}</span> <b>{g["hs"]}-{g["as"]}</b> '
                 f'<span style="{"color:#7A84A3" if hw else "font-weight:800"}">{E(club(g["away"]))}</span></td>'
                 f'<td align="right" style="padding:9px 0;border-bottom:1px solid #E8ECF5"><a href="{vote}?m={g["id"]}" style="font:800 13px Arial,Helvetica,sans-serif;color:#002395;text-decoration:none">NOTER ›</a></td></tr>')
    a(f'<tr><td style="padding:0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table></td></tr>')
    # lecteurs vs nous
    if B["gaps"]:
        a(h2("Lecteurs contre EuroLeague France", "Vos votes"))
        rows = "".join(f'<tr><td style="padding:8px 0;border-bottom:1px solid #E8ECF5;font:15px Arial,Helvetica,sans-serif;color:#1B2440"><b>{E(pn(n[0]))}</b><br><span style="color:#7A84A3;font-size:13px">{r[1]} votes</span></td><td align="right" style="padding:8px 0;border-bottom:1px solid #E8ECF5;font:13px Arial,Helvetica,sans-serif;color:#7A84A3">Nous {chip(n[6], 14)} &nbsp; Vous {chip(r[0], 14)}</td></tr>' for _, n, r in B["gaps"])
        a(f'<tr><td style="padding:0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table></td></tr>')
    # classement
    if B["std"]:
        a(h2("Le classement", "Le haut du tableau"))
        rows = "".join(f'<tr><td style="padding:6px 0;border-bottom:1px solid #E8ECF5;font:14px Arial,Helvetica,sans-serif;color:#1B2440"><b style="display:inline-block;width:24px">{r[0]}</b>{E(club(r[1]))}</td><td align="right" style="padding:6px 0;border-bottom:1px solid #E8ECF5;font:14px Arial,Helvetica,sans-serif;color:#1B2440"><b>{r[3]}-{r[4]}</b> <span style="color:#7A84A3">({r[5]})</span></td></tr>' for r in B["std"])
        a(f'<tr><td style="padding:0 28px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table></td></tr>')
    # fantasy
    if B["fx"] or B["inj"]:
        a(h2(f"Fantasy : prépare la J{B['nxt']}" if B["nxt"] else "Fantasy", "Fantasy Challenge"))
        if B["fx"]:
            days = sorted({x[1] for x in B["fx"]})
            fxs = " · ".join(f'{E(club(x[2]))}–{E(club(x[3]))}' for x in B["fx"])
            a(f'<tr><td style="padding:0 28px 8px;font:14px/1.6 Arial,Helvetica,sans-serif;color:#1B2440"><b>Au programme ({" et ".join(dfr(x) for x in days)})</b><br>{fxs}</td></tr>')
        if B["inj"]:
            S = {"out": ("Forfait", "#A01E16"), "doubt": ("Incertain", "#B08816")}
            rows = "".join(f'<tr><td style="padding:7px 0;border-bottom:1px solid #E8ECF5;font:14px Arial,Helvetica,sans-serif;color:#1B2440"><b>{E(x["n"])}</b> <span style="color:#7A84A3">· {E(club(x["c"]))}</span><br><span style="color:#7A84A3;font-size:12px">{E(x["t"])}</span></td><td align="right" style="padding:7px 0;border-bottom:1px solid #E8ECF5"><span style="font:800 11px Arial,Helvetica,sans-serif;color:#fff;background:{S[x["s"]][1]};padding:4px 7px;border-radius:6px">{S[x["s"]][0].upper()}</span></td></tr>' for x in B["inj"])
            a(f'<tr><td style="padding:0 28px"><div style="font:800 14px Arial,Helvetica,sans-serif;color:#1B2440;margin:6px 0 2px">Blessés et incertains à surveiller</div><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table></td></tr>')
    # vidéo
    v = B["vid"]
    if v:
        a(h2("La dernière vidéo", "YouTube"))
        a(f'<tr><td style="padding:0 28px"><a href="https://www.youtube.com/watch?v={v["id"]}" style="text-decoration:none;color:#1B2440"><img src="https://i.ytimg.com/vi/{v["id"]}/hqdefault.jpg" width="544" alt="" style="display:block;width:100%;height:auto;border-radius:12px;border:0"><div style="font:800 16px/1.35 Arial,Helvetica,sans-serif;margin-top:8px">▶ {E(v["title"])}</div></a></td></tr>')
    # appel
    a(f'''<tr><td align="center" style="padding:34px 28px 10px"><a href="{vote}" style="display:inline-block;background:#FFB547;color:#1B1300;font:800 17px Arial,Helvetica,sans-serif;text-decoration:none;padding:16px 28px;border-radius:12px;letter-spacing:1px">NOTE LES JOUEURS DE LA SEMAINE</a>
<div style="font:14px Arial,Helvetica,sans-serif;color:#7A84A3;margin-top:12px"><a href="{notes}" style="color:#002395">Toutes nos notes</a> · <a href="https://www.euroleague-france.com/fantasy-challenge/" style="color:#002395">Fantasy</a> · <a href="https://x.com/EuroLeagueFr" style="color:#002395">X</a> · <a href="https://www.instagram.com/euroleague_fr/" style="color:#002395">Instagram</a></div></td></tr>
<tr><td style="padding:22px 28px 26px;font:12px/1.5 Arial,Helvetica,sans-serif;color:#9AA3BF;text-align:center">Tu reçois cette lettre car tu fais partie du réseau EuroLeague France. Notes calculées par notre formule à partir des statistiques officielles EuroLeague.</td></tr>
</table></td></tr></table></body></html>''')
    subj = f"{pn(B['mvp'][0])} {nfr(B['mvp'][6])}/10 : la lettre de la {B['rshort']}"
    return "\n".join(T), subj, pre

def run_build(day):
    B = build(day)
    if not B: return 1
    os.makedirs(os.path.join(ROOT, "og", "nl"), exist_ok=True); os.makedirs(os.path.join(ROOT, "newsletter"), exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 640})
        pg.goto("file://" + os.path.join(ROOT, "robot", "share", "cinq.html"))
        pg.evaluate("D=>window.render(D)", B["card"]); pg.wait_for_timeout(300)
        pg.screenshot(path=os.path.join(ROOT, "og", "nl", f"{day}-cinq.jpg"), type="jpeg", quality=88); b.close()
    body, subj, pre = html_email(B, day)
    open(os.path.join(ROOT, "newsletter", f"{day}.html"), "w", encoding="utf-8").write(body)
    json.dump({"date": day, "subject": subj, "preview": pre, "web": f"{SITE}/newsletter/{day}.html"},
              open(os.path.join(ROOT, "robot", "newsletter_meta.json"), "w"), ensure_ascii=False, indent=1)
    print("lettre fabriquée :", subj)
    return 0

def span(W):
    a, b = W["start"], W["end"]
    if a == b: return f"le {dfr(a.isoformat())}"
    if a.month == b.month: return f"du {'1er' if a.day == 1 else a.day} au {dfr(b.isoformat())}"
    return f"du {dfr(a.isoformat())} au {dfr(b.isoformat())}"

def notify():
    topic = os.environ.get("NTFY_TOPIC"); meta = json.load(open(os.path.join(ROOT, "robot", "newsletter_meta.json")))
    if not topic: print("::warning::NTFY_TOPIC absent"); return 0
    kit = "https://app.kit.com/campaigns" 
    msg = {"topic": topic, "title": "Lettre du samedi prête", "message": meta["subject"] + ("\n\nBrouillon prêt dans Kit : relis puis envoie." if meta.get("kit") else "\n\nPas de brouillon Kit (clé absente ou test) : aperçu seulement.") + "\nVersion web : " + meta["web"],
           "click": meta["web"], "tags": ["email"], "actions": [{"action": "view", "label": "Ouvrir Kit", "url": kit}, {"action": "view", "label": "Voir la lettre", "url": meta["web"]}]}
    req = urllib.request.Request("https://ntfy.sh/", data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r: print("notifié", r.status)
    return 0

def draft():
    key = os.environ.get("KIT_API_KEY")
    meta = json.load(open(os.path.join(ROOT, "robot", "newsletter_meta.json")))
    body = open(os.path.join(ROOT, "newsletter", f"{meta['date']}.html"), encoding="utf-8").read()
    if not key: print("::warning::KIT_API_KEY absent : brouillon non créé (lettre en ligne :", meta["web"], ")"); return 0
    req = urllib.request.Request("https://api.kit.com/v4/broadcasts", method="POST",
        data=json.dumps({"subject": meta["subject"], "preview_text": meta["preview"], "content": body, "public": False,
                         "description": f"Lettre automatique {meta['date']}", "send_at": None}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json", "X-Kit-Api-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print("::error::Kit a refusé le brouillon :", e.code, e.read().decode()[:400]); return 1
    print("brouillon Kit créé", res.get("broadcast", {}).get("id"))
    meta["kit"] = True; json.dump(meta, open(os.path.join(ROOT, "robot", "newsletter_meta.json"), "w"), ensure_ascii=False, indent=1)
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    day = a[a.index("--date") + 1] if "--date" in a else dt.date.today().isoformat()
    if a[0] == "build": sys.exit(run_build(day))
    elif a[0] == "draft": sys.exit(draft())
    elif a[0] == "notify": sys.exit(notify())
