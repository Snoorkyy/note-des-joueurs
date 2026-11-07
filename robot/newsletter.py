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

def B_short(W): return "J" + "-J".join(str(r) for r in W["rounds"])
def span_short(W):
    a, b = W["start"], W["end"]; M = MOIS[b.month - 1][:4].rstrip(".")
    return f"{a.day}–{b.day} {MOIS[b.month-1]}" if a.month == b.month and a != b else dfr(b.isoformat())

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
    heads = {}
    pp = get("https://api-live.euroleague.net/v2/competitions/E/seasons/E%d/people?personType=J" % int(W["end"].year if W["end"].month >= 8 else W["end"].year - 1))
    for x in (pp or {}).get("data", pp if isinstance(pp, list) else []):
        try: heads["P" + x["person"]["code"]] = (x.get("images") or {}).get("headshot")
        except Exception: pass
    card = {"pill": f"{B_short(W)} · {span_short(W)}".upper(), "sub": f"Les 5 meilleures notes · {len(W['ms'])} matchs",
            "five": [{"id": n[0], "n": pn(n[0]), "note": n[6], "photo": n[0] in W["ph"], "club": n[2], "fra": n[0] in W["frs"], "cut": heads.get(n[0]),
                      "mt": f"{n[4]} d'éval · {Math.r(n[3])} min · vs {club(opp(W, n))}"} for n in five]}
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

F = "font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;"
def chip(n, size=16, w=44):
    return (f'<span style="display:inline-block;min-width:{w}px;padding:6px 8px;border-radius:9px;background:{NC(n)};color:#fff;'
            f'{F}font-weight:800;font-size:{size}px;line-height:1;text-align:center">{nfr(round(n * 2) / 2)}</span>')

def card(eyebrow, title, inner):
    return (f'<tr><td style="padding:0 20px 16px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#111C4A;background-color:#111C4A;border-radius:18px">'
            f'<tr><td style="padding:22px 22px 6px"><div style="{F}font-size:12px;font-weight:800;letter-spacing:3px;color:#FFB547;text-transform:uppercase">{eyebrow}</div>'
            f'<div style="{F}font-size:24px;line-height:1.1;font-weight:800;color:#FFFFFF;text-transform:uppercase;margin-top:4px">{title}</div></td></tr>'
            f'<tr><td style="padding:8px 22px 20px">{inner}</td></tr></table></td></tr>')

def rows(items):
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">' + "".join(
        f'<tr><td style="padding:11px 0;border-top:1px solid rgba(255,255,255,.08);border-top-color:#22305F;{F}font-size:15px;line-height:1.35;color:#FFFFFF">{l}</td>'
        f'<td align="right" style="padding:11px 0 11px 10px;border-top:1px solid #22305F;white-space:nowrap">{r}</td></tr>' for l, r in items) + '</table>'

def social():
    def pill(href, bg, label, fg="#FFFFFF", border="transparent"):
        return (f'<a href="{href}" style="display:inline-block;margin:4px;padding:11px 16px;border-radius:999px;background:{bg};background-color:{bg.split(",")[-1].strip(") ") if "gradient" in bg else bg};'
                f'border:1px solid {border};color:{fg};{F}font-size:14px;font-weight:800;text-decoration:none;letter-spacing:.5px">{label}</a>')
    return (pill("https://x.com/EuroLeagueFr", "#000000", "𝕏&nbsp; @EuroLeagueFr", border="#3A4570")
            + pill("https://www.instagram.com/euroleague_fr/", "linear-gradient(45deg,#F58529,#DD2A7B,#8134AF,#515BD4)", "◎&nbsp; Instagram · @euroleague_fr")
            + pill("https://www.youtube.com/@EuroLeagueFrance", "#E62117", "▶&nbsp; YouTube"))

def html_email(B, day):
    d, W, pn, club = B["d"], B["W"], B["pn"], B["club"]
    img = f"{SITE}/og/nl/{day}-cinq.jpg"; vote = f"{SITE}/vote.html"; notes = f"{NOTES}#journee-{W['rounds'][-1]}"
    m, f = B["mvp"], B["flop"]
    pre = f"{pn(m[0])} {nfr(m[6])}/10, le cinq de la semaine, les Français et la fantasy de la {B['rshort']}."
    T = []; a = T.append
    a(f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark light"><meta name="supported-color-schemes" content="dark light"><title>La lettre EuroLeague France · {B['rshort']}</title></head>
<body style="margin:0;padding:0;background:#05091C;background-color:#05091C">
<div style="display:none;max-height:0;overflow:hidden">{E(pre)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#05091C;background-color:#05091C"><tr><td align="center" style="padding:18px 8px 30px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:#0A1236;background-color:#0A1236;border-radius:22px;overflow:hidden">
<tr><td style="padding:22px 24px 18px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
 <td><a href="{NOTES}"><img src="{SITE}/logo_white.png" alt="EuroLeague France" height="36" style="display:block;height:36px;border:0"></a></td>
 <td align="right" style="{F}font-size:12px;font-weight:800;letter-spacing:2px;color:#8E9AC4;text-transform:uppercase">La lettre du samedi<br><span style="color:#FFB547">{E(B['rshort'])} · {E(span_short(W))}</span></td></tr></table></td></tr>
<tr><td><a href="{notes}"><img src="{img}" width="600" alt="Le cinq de la semaine : {E(', '.join(pn(n[0]) for n in B['five']))}" style="display:block;width:100%;height:auto;border:0"></a></td></tr>
<tr><td style="padding:28px 24px 22px">
 <div style="{F}font-size:34px;line-height:1.02;font-weight:800;color:#FFFFFF;text-transform:uppercase;letter-spacing:-.5px">{E(pn(m[0]))} <span style="color:#FFB547">a régné</span> sur la {E(B['rshort'])}</div>
 <div style="{F}font-size:16px;line-height:1.55;color:#AEB9E0;margin-top:12px">{len(W['ms'])} matchs, {len(W['N'])} joueurs notés {span(W)}. Ton résumé en 2 minutes, et à toi de noter.</div>
 <a href="{vote}" style="display:inline-block;margin-top:18px;padding:14px 22px;border-radius:12px;background:#FFB547;background-color:#FFB547;color:#140C00;{F}font-size:15px;font-weight:800;letter-spacing:1px;text-decoration:none">NOTER LES JOUEURS →</a>
</td></tr>""")
    # MVP / flop
    def big(lbl, n, col):
        return (f'<td width="50%" valign="top" style="padding:0 6px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{col};background-color:{col};border-radius:16px">'
                f'<tr><td style="padding:16px"><div style="{F}font-size:11px;font-weight:800;letter-spacing:2px;color:rgba(255,255,255,.75)">{lbl}</div>'
                f'<div style="{F}font-size:20px;line-height:1.05;font-weight:800;color:#fff;text-transform:uppercase;margin:6px 0 4px">{E(pn(n[0]))}</div>'
                f'<div style="{F}font-size:13px;color:rgba(255,255,255,.8)">{E(club(n[2]))} · {n[4]} d\'éval · {Math.r(n[3])} min</div>'
                f'<div style="{F}font-size:40px;font-weight:800;color:#fff;margin-top:8px">{nfr(round(n[6]*2)/2)}<span style="font-size:16px;opacity:.7">/10</span></div></td></tr></table></td>')
    a(f'<tr><td style="padding:0 14px 16px"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{big("★ MVP DE LA SEMAINE", m, "#1E6B40")}{big("▼ FLOP DE LA SEMAINE", f, "#8E1B15")}</tr></table></td></tr>')
    if B["fr_rows"]:
        a(card("🇫🇷 Nos joueurs", "Les Français", rows([(f'<b>{E(pn(n[0]))}</b><br><span style="color:#8E9AC4;font-size:13px">{E(club(n[2]))} vs {E(club(opp(W, n)))} · {Math.r(n[3])} min</span>', chip(n[6])) for n in B["fr_rows"][:10]])))
    res = []
    for g in W["ms"]:
        hw = g["hs"] > g["as"]
        L = (f'<span style="{"" if hw else "color:#8E9AC4"}">{E(club(g["home"]))}</span> <b style="color:#FFB547">{g["hs"]}-{g["as"]}</b> '
             f'<span style="{"color:#8E9AC4" if hw else ""}">{E(club(g["away"]))}</span>')
        res.append((L, f'<a href="{vote}?m={g["id"]}" style="display:inline-block;padding:7px 12px;border-radius:999px;border:1px solid #FFB547;color:#FFB547;{F}font-size:12px;font-weight:800;text-decoration:none">NOTER</a>'))
    a(card("Les scores", "À toi de noter chaque match", rows(res)))
    if B["gaps"]:
        a(card("Vos votes", "Lecteurs contre EuroLeague France", rows([(f'<b>{E(pn(n[0]))}</b><br><span style="color:#8E9AC4;font-size:13px">{r[1]} votes</span>',
            f'<span style="{F}font-size:11px;color:#8E9AC4">NOUS</span> {chip(n[6], 14, 36)} &nbsp;<span style="{F}font-size:11px;color:#8E9AC4">VOUS</span> {chip(r[0], 14, 36)}') for _, n, r in B["gaps"]])))
    if B["std"]:
        a(card("Classement", "Le haut du tableau", rows([(f'<span style="display:inline-block;width:26px;color:#FFB547;font-weight:800">{r[0]}</span>{E(club(r[1]))}',
            f'<span style="{F}font-size:15px;color:#fff;font-weight:800">{r[3]}-{r[4]}</span> <span style="{F}font-size:13px;color:#8E9AC4">{r[5]}</span>') for r in B["std"]])))
    if B["fx"] or B["inj"]:
        inner = ""
        if B["fx"]:
            days = sorted({x[1] for x in B["fx"]})
            inner += (f'<div style="{F}font-size:13px;font-weight:800;color:#8E9AC4;letter-spacing:1px;text-transform:uppercase;margin-bottom:6px">Au programme · {" et ".join(dfr(x) for x in days)}</div>'
                      f'<div style="{F}font-size:15px;line-height:1.7;color:#fff;margin-bottom:12px">' + "<br>".join(f'{E(club(x[2]))} – {E(club(x[3]))}' for x in B["fx"]) + '</div>')
        if B["inj"]:
            S = {"out": ("FORFAIT", "#A01E16"), "doubt": ("INCERTAIN", "#B08816")}
            inner += f'<div style="{F}font-size:13px;font-weight:800;color:#8E9AC4;letter-spacing:1px;text-transform:uppercase">À surveiller</div>' + rows(
                [(f'<b>{E(x["n"])}</b> <span style="color:#8E9AC4">· {E(club(x["c"]))}</span><br><span style="color:#8E9AC4;font-size:12px">{E(x["t"])}</span>',
                  f'<span style="{F}font-size:11px;font-weight:800;color:#fff;background:{S[x["s"]][1]};padding:5px 8px;border-radius:7px">{S[x["s"]][0]}</span>') for x in B["inj"]])
        inner += f'<a href="https://www.euroleague-france.com/fantasy-challenge/" style="display:inline-block;margin-top:14px;{F}font-size:14px;font-weight:800;color:#FFB547;text-decoration:none">Projections et crédits de la J{B["nxt"]} →</a>'
        a(card("Fantasy Challenge", f"Prépare la J{B['nxt']}" if B["nxt"] else "Fantasy", inner))
    v = B["vid"]
    if v:
        a(card("YouTube", "La dernière émission", f'<a href="https://www.youtube.com/watch?v={v["id"]}" style="text-decoration:none"><img src="https://i.ytimg.com/vi/{v["id"]}/hqdefault.jpg" width="512" alt="" style="display:block;width:100%;height:auto;border-radius:12px;border:0">'
                f'<div style="{F}font-size:16px;line-height:1.35;font-weight:800;color:#fff;margin-top:10px">▶ {E(v["title"])}</div></a>'))
    a(f"""<tr><td align="center" style="padding:14px 24px 8px">
 <a href="{vote}" style="display:block;padding:18px;border-radius:14px;background:#FFB547;background-color:#FFB547;color:#140C00;{F}font-size:18px;font-weight:800;letter-spacing:1px;text-decoration:none;text-align:center">À TOI DE NOTER LES JOUEURS</a></td></tr>
<tr><td align="center" style="padding:22px 16px 6px"><div style="{F}font-size:12px;font-weight:800;letter-spacing:3px;color:#8E9AC4;margin-bottom:8px">SUIS-NOUS</div>{social()}</td></tr>
<tr><td style="padding:20px 28px 26px;{F}font-size:12px;line-height:1.6;color:#6F7AA3;text-align:center">Tu reçois la lettre du samedi d'EuroLeague France.<br>Notes calculées par notre formule à partir des statistiques officielles EuroLeague. <a href="{SITE}/newsletter/{day}.html" style="color:#8E9AC4">Version web</a></td></tr>
<tr><td style="height:6px;background:#002395;background-image:linear-gradient(90deg,#002395 0 33%,#ffffff 33% 66%,#ED2939 66%)"></td></tr>
</table></td></tr></table></body></html>""")
    subj = f"{pn(m[0])} {nfr(m[6])}/10 : la lettre de la {B['rshort']}"
    return "\n".join(T), subj, pre

def run_build(day):
    B = build(day)
    if not B: return 1
    os.makedirs(os.path.join(ROOT, "og", "nl"), exist_ok=True); os.makedirs(os.path.join(ROOT, "newsletter"), exist_ok=True)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1200, "height": 1300})
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
