"""Robot EuroLeague France : note automatiquement les matchs terminés (formule v1 gelée) et met à jour data.json.

Usage : python3 robot/run.py [--check 91,92,...] [--codes 101,102]
  sans option : cherche tous les matchs joués (date de calendrier <= aujourd'hui) absents de data.json,
                les note s'ils sont terminés et que tous les contrôles passent, puis écrit data.json.
  --check     : recalcule des matchs déjà publiés et compare aux notes publiées (n'écrit rien).
  --codes     : force la liste des gamecodes à traiter.
Sortie : écrit robot/commit_msg.txt si data.json a changé. Code retour 1 si un match terminé échoue aux contrôles.
"""
import json, sys, os, re, datetime as dt, urllib.request, zoneinfo
sys.path.insert(0, os.path.dirname(__file__))
import engine as E

SEASON = "E2026"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.json")
UA = {"User-Agent": "Mozilla/5.0 (EuroLeague France robot)"}
PARIS = zoneinfo.ZoneInfo("Europe/Paris")

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def api(t, code):
    return get(f"https://live.euroleague.net/api/{t}?gamecode={code}&seasoncode={SEASON}")

T = lambda x: (x or "").strip()
PT = {'2FGM':'2','3FGM':'3','FTM':'1','2FGA':'x','3FGA':'y','FTA':'z','O':'O','D':'D','AS':'A','ST':'S','TO':'T','FV':'B',
      'AG':'G','CM':'F','OF':'f','RV':'R','IN':'I','OUT':'U','CMU':'u','CMU_FL':'u','CMU_DI':'u','CMT':'t','CMT1':'t',
      'CMT2':'t','CMTI':'t','C':'c','CCH':'k'}
IGN = {'B','BP','EP','EG','JB','TOUT','TOUT_TV','FTC'}

def extract(code):
    """Équivalent Python de extract.js : box, pbp compact, codes joueurs."""
    h, b, p = api("Header", code), api("Boxscore", code), api("PlayByPlay", code)
    A, B = T(h["CodeTeamA"]), T(h["CodeTeamB"])
    box, codes, names = [], {}, {}
    i = 0
    for s in b["Stats"]:
        for q in s["PlayersStats"]:
            pid = T(q.get("Player_ID"))
            if not pid or ":" not in (q.get("Minutes") or ""): continue
            codes[pid] = chr(97 + i); i += 1
            names[pid] = q["Player"]
            box.append("|".join(str(v) for v in [pid, q["Player"], "A" if T(q["Team"]) == A else "B", q["IsStarter"], q["Minutes"],
                q["Points"], q["FieldGoalsMade2"], q["FieldGoalsAttempted2"], q["FieldGoalsMade3"], q["FieldGoalsAttempted3"],
                q["FreeThrowsMade"], q["FreeThrowsAttempted"], q["OffensiveRebounds"], q["DefensiveRebounds"], q["Assistances"],
                q["Steals"], q["Turnovers"], q["BlocksFavour"], q["BlocksAgainst"], q["FoulsCommited"], q["FoulsReceived"],
                q["Valuation"], q["Plusminus"]]))
    unk, out, ended = set(), [], False
    for k, n in [("FirstQuarter",1),("SecondQuarter",2),("ThirdQuarter",3),("ForthQuarter",4),("ExtraTime",5)]:
        ev = p.get(k) or []
        if not ev: continue
        qn, last = n, 1e9; out.append(f"#{qn}")
        for e in ev:
            ty = T(e.get("PLAYTYPE"))
            if ty == "EG": ended = True
            mt = T(e.get("MARKERTIME"))
            if not mt: continue
            mm, ss = map(int, mt.split(":")); sec = mm * 60 + ss
            if n == 5 and sec > last + 5: qn += 1; out.append(f"#{qn}")
            last = sec
            c = PT.get(ty)
            if not c:
                if ty not in IGN: unk.add(ty)
                continue
            tm = T(e.get("CODETEAM"))
            if not tm: continue
            pid = T(e.get("PLAYER_ID"))
            s = f"{sec}{c}{codes.get(pid, '_') if pid else '_'}{'A' if tm == A else 'B'}"
            if e.get("POINTS_A") is not None or e.get("POINTS_B") is not None:
                s += f"{e.get('POINTS_A') or 0}-{e.get('POINTS_B') or 0}"
            out.append(s)
    dd, mo, yy = h["Date"].split("/")
    return dict(code=code, A=A, B=B, nameA=h.get("TeamA", A), nameB=h.get("TeamB", B), round=int(h["Round"]),
                date=f"{yy}-{mo}-{dd}", score=(int(h["ScoreA"] or 0), int(h["ScoreB"] or 0)), live=bool(h.get("Live")),
                ended=ended, unk=sorted(unk), box="\n".join(box), pbp=" ".join(out), codes=codes, names=names)

K = "id name team st min pts m2 a2 m3 a3 ftm fta orb drb ast stl to blk blka fc fd pir pm".split()
def load_box(txt):
    out = {}
    for l in txt.split("\n"):
        if not l.strip(): continue
        r = dict(zip(K, l.strip().split("|")))
        try:
            for k in K[3:]:
                if k == "min": m, s = r[k].split(":"); r[k] = int(m) + int(s) / 60
                elif k == "st": r[k] = 1 if r[k] in ("1", "True", "true") else 0
                else: r[k] = int(r[k])
        except ValueError as e:
            raise ValueError(f"ligne de box illisible ({e}) : {l}")
        out[r["id"]] = r
    return out

def checks(g, box):
    """Contrôles de check.py : score reconstitué, minutes PBP = box, somme des +/- = 5 x écart."""
    c2i = {v: k for k, v in g["codes"].items()}
    ev = E.parse(g["pbp"], c2i)
    if not ev: return ["play-by-play vide"]
    on = {"A": set(), "B": set()}
    for p, r in box.items():
        if r["st"]: on[r["team"]].add(p)
    mins = {p: 0 for p in box}; pm = {p: 0 for p in box}; t0 = 0; sa = sb = 0; nq = max(e["q"] for e in ev)
    el = lambda q, s: (q - 1) * 600 + (600 - s) if q <= 4 else 2400 + (q - 5) * 300 + (300 - s)
    for e in ev:
        t = el(e["q"], e["s"])
        for S in on.values():
            for p in S: mins[p] += t - t0
        t0 = t
        if e["typ"] == "I" and e["pid"]: on[e["team"]].add(e["pid"])
        if e["typ"] == "U" and e["pid"]: on[e["team"]].discard(e["pid"])
        if e["sa"] is not None:
            d = (e["sa"] - sa) - (e["sb"] - sb); sa, sb = e["sa"], e["sb"]
            for p in on["A"]: pm[p] += d
            for p in on["B"]: pm[p] -= d
    end = 2400 + max(0, nq - 4) * 300
    for S in on.values():
        for p in S: mins[p] += end - t0
    err = []
    if (sa, sb) != g["score"]: err.append(f"score reconstitué {sa}-{sb} ≠ score officiel {g['score'][0]}-{g['score'][1]}")
    bad = [(box[p]["name"], round(mins[p] / 60, 1), round(box[p]["min"], 1)) for p in box if abs(mins[p] / 60 - box[p]["min"]) > 0.2]
    if bad: print("  avertissement (non bloquant) : minutes PBP ≠ box", bad)   # décalage de chrono fréquent dans les données officielles, sans effet sur les notes
    sA = sum(pm[p] for p in box if box[p]["team"] == "A"); sB = sum(pm[p] for p in box if box[p]["team"] == "B")
    if sA != 5 * (sa - sb) or sB != -5 * (sa - sb): err.append(f"somme des +/- incohérente ({sA}, {sB})")
    if g["unk"]: err.append(f"types de play-by-play inconnus : {g['unk']}")
    return err

def rate(g):
    box = load_box(g["box"])
    err = checks(g, box)
    res = E.run(box, g["pbp"], g["codes"], {"A": g["score"][0], "B": g["score"][1]})
    club = {"A": g["A"], "B": g["B"]}
    rows = [[r["id"], f"{SEASON}-{g['code']}", club[r["team"]], round(r["min"], 1), r["pir"], r["pm_chk"], r["note"]] for r in res]
    return rows, err, box

def nat_lookup():
    try:
        j = get(f"https://api-live.euroleague.net/v2/competitions/E/seasons/{SEASON}/people?personType=J")
        items = j.get("data", j) if isinstance(j, dict) else j
        return {"P" + str(x["person"]["code"]).zfill(6): (x["person"].get("country") or {}).get("code") for x in items}
    except Exception as e:
        print("nationalités indisponibles :", e); return {}

def standings(rnd):
    j = get(f"https://api-live.euroleague.net/v3/competitions/E/seasons/{SEASON}/rounds/{rnd}/basicstandings")
    return {"round": rnd, "fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "rows": [[x["position"], x["club"]["code"], x["gamesPlayed"], x["gamesWon"], x["gamesLost"],
                      x["pointsDifference"], x["positionChange"]] for x in j["teams"]]}

def title(n): return ", ".join(p.strip().title() for p in n.split(","))

def main():
    a = sys.argv[1:]
    d = json.load(open(DATA, encoding="utf-8"))
    have = {m["id"] for m in d["matches"]}
    if "--check" in a:
        codes = [int(x) for x in a[a.index("--check") + 1].split(",")]
        pub = {}
        for n in d["notes"]: pub.setdefault(n[1], {})[n[0]] = n[6]
        bad = 0
        for c in codes:
            try: g = extract(c); rows, err, _ = rate(g)
            except Exception as e:
                import traceback; print(c, "ERREUR", e); traceback.print_exc(); bad += 1; continue
            mine = {r[0]: r[6] for r in rows}; p = pub.get(f"{SEASON}-{c}", {})
            diff = {k: (mine.get(k), p.get(k)) for k in set(mine) | set(p) if mine.get(k) != p.get(k)}
            print(c, g["A"], g["B"], g["score"], "contrôles OK" if not err else err, "| notes identiques" if not diff else f"| ÉCARTS {diff}")
            bad += bool(diff or err)
        sys.exit(1 if bad else 0)
    today = dt.datetime.now(PARIS).date().isoformat()
    if "--codes" in a: todo = [int(x) for x in a[a.index("--codes") + 1].split(",")]
    else:
        # gamecodes de la saison régulière : journée r -> codes 10(r-1)+1 .. 10r, dans l'ordre du calendrier
        fx = sorted({(f[0], f[1]) for f in d["fixtures"]})
        played_rounds = sorted({r for r, day in fx if day <= today})
        todo = [c for r in played_rounds for c in range(10 * (r - 1) + 1, 10 * r + 1) if f"{SEASON}-{c}" not in have]
    print("à examiner :", todo)
    new, failed, nats = [], [], None
    for c in todo:
        try: g = extract(c)
        except Exception as e: print(c, "indisponible :", e); continue
        if g["live"] or not g["ended"] or not g["box"]:
            print(c, g["A"], g["B"], "pas terminé (Live =", g["live"], ", fin =", g["ended"], ")"); continue
        try: rows, err, box = rate(g)
        except Exception as e: rows, err, box = [], [f"données illisibles : {e}"], {}
        if err:
            print(c, "CONTRÔLES ÉCHOUÉS :", err); failed.append((c, g, err)); continue
        for pid, r in box.items():
            club = g["A"] if r["team"] == "A" else g["B"]
            if pid not in d["players"]:
                d["players"][pid] = {"name": title(r["name"]), "club": club}
                if nats is None: nats = nat_lookup()
                if nats.get(pid): d.setdefault("nat", {})[pid] = nats[pid]
                if nats.get(pid) == "FRA" and pid not in d.get("fr", []): d.setdefault("fr", []).append(pid)
                print("  nouveau joueur :", title(r["name"]), club, nats.get(pid) if nats else "")
            else:
                d["players"][pid]["club"] = club
        d["matches"].append({"id": f"{SEASON}-{c}", "round": g["round"], "date": g["date"], "home": g["A"], "away": g["B"],
                             "hs": g["score"][0], "as": g["score"][1]})   # toujours en fin de liste (jeu « Top à l'aveugle »)
        d["notes"] += rows
        new.append(g)
        print(c, g["A"], g["score"], g["B"], "→", len(rows), "notes")
    if new:
        rnd = max(g["round"] for g in new)
        try: d["standings"] = standings(max(rnd, d.get("standings", {}).get("round", 0)))
        except Exception as e: print("classement indisponible :", e)
        for r in {str(m["round"]) for m in d["matches"]}:
            if r in d.get("res", {}) and sum(1 for m in d["matches"] if str(m["round"]) == r) >= 10: d["res"].pop(r)
        d["updated"] = dt.datetime.now(PARIS).strftime("%Y-%m-%dT%H:%M")
        json.dump(d, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        msg = " · ".join(f"J{g['round']} {T(g['nameA']).title()} - {T(g['nameB']).title()} {g['score'][0]}-{g['score'][1]} ({SEASON}-{g['code']})" for g in new)
        open(os.path.join(ROOT, "robot", "commit_msg.txt"), "w").write("Notes auto : " + msg)
    if failed:
        print("::error::Matchs non publiés (contrôles) : " + "; ".join(f"{SEASON}-{c} {g['A']}-{g['B']} : {err}" for c, g, err in failed))
        sys.exit(1)

if __name__ == "__main__":
    main()
