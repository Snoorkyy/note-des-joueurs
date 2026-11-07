"""Championnat public « EuroLeague France » du EuroLeague Fantasy Challenge (API Dunkest/Fantaking).

La configuration (journées) est publique ; le classement et les effectifs demandent le jeton de session d'un compte
membre du championnat : secret GitHub FANTASY_TOKEN (valeur de « flutter.authToken » du site du jeu, sans guillemets).
Sans jeton, fetch() renvoie None et la lettre n'affiche que les lots et le lien pour rejoindre."""
import json, os, unicodedata, urllib.request

API = "https://fantaking-api.dunkest.com/api/v1"
LEAGUE, TOURNAMENT = 10, 192516
JOIN = "https://euroleaguefantasy.euroleaguebasketball.net/10/fantasy/2658060/192516"

# Lots du championnat (liste fournie par EuroLeague France, identique à la page Fantasy du site)
# [mois (1-12), (journée début, journée fin), [(lot, gagnant)]] ; gagnant = code ou numéro de journée
LOTM = [(9, (1, 2), [("tv", "b12"), ("tk", "g2"), ("tk", 2)]), (10, (3, 9), [("tv", "bm"), ("tk", "g2"), ("tk", 7)]),
        (11, (9, 14), [("tv", "bm"), ("tk", "g2"), ("tk", 13)]), (12, (15, 20), [("tv", "bm"), ("tk", "g2"), ("tk", 19), ("tk", 20)]),
        (1, (21, 25), [("je", "bm"), ("tk", "m2"), ("tk", 24)]), (2, (26, 28), [("ca", "bm"), ("tk", "m2"), ("tk", 27)]),
        (3, (29, 34), [("je", "bm"), ("tk", "m2"), ("tk", 33)]), (4, (35, 38), [("c2", "top2")])]
PRIZE = {"tv": ("📺", "Un pass EuroLeague TV"), "tk": ("🎟️", "2 places pour un match d'EuroLeague au choix (Paris ou ASVEL)"),
         "je": ("👕", "Un maillot"), "ca": ("🧢", "Une casquette"), "c2": ("🧢", "2 casquettes")}
WHO = {"b12": "Meilleur score cumulé J1 + J2", "g2": "2e du classement général", "bm": "Meilleur score du mois",
       "m2": "2e du mois", "top2": "Les 2 premiers du mois"}
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]

def lots(month):
    for m, (a, b), L in LOTM:
        if m == month:
            return {"month": MONTHS[m - 1], "from": a, "to": b,
                    "items": [(PRIZE[p][0], PRIZE[p][1], WHO[w] if isinstance(w, str) else f"Meilleur score de la J{w}") for p, w in L],
                    "season": ("🏆", "Un trophée EuroLeague miniature", "Vainqueur du classement général final")}
    return None

def _get(path, token=None):
    h = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    if token: h["Authorization"] = "Bearer " + token
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=h), timeout=30) as r:
        return json.loads(r.read().decode())

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace("-", " ").replace(".", " ").split())

def fetch(token=None):
    """-> dict(md, overall[10], round_top[3], best{team, coach, pts, players[...]}) ou None."""
    raw = token or os.environ.get("FANTASY_TOKEN") or ""
    token = raw.strip().strip('"').strip("'").strip()
    if token.lower().startswith("bearer "): token = token[7:].strip()
    if raw: print(f"jeton fantasy : {len(raw)} caractères reçus, {len(token)} après nettoyage, forme {'id|clé' if '|' in token else 'autre'}")
    cfg = _get(f"/leagues/{LEAGUE}/config")["data"]
    prev = cfg.get("previous_matchday") or {}
    out = {"md": prev.get("number"), "md_id": prev.get("id"), "teams": {t["id"]: t for t in cfg.get("teams", [])}}
    if os.environ.get("FANTASY_DEMO"):  # test du visuel sans jeton : équipe réelle de la J8 (CSP Lausanne)
        P = [["Aliou","Diarra","VIR","Virtus Bologna","Center",16,0,1],["Azuolas","Tubelis","ZAL","Zalgiris Kaunas","Forward",23.1,0,2],["Dwayne","Bacon","DUB","Dubai Basketball","Forward",27,0,3],
             ["Elijah","Bryant","HTA","Hapoel Tel Aviv","Guard",38.5,1,4],["Theo","Maledon","RMB","Real Madrid","Guard",17.6,0,5],["Andres","Feliz","RMB","Real Madrid","Guard",9.9,0,6],
             ["Josep","Puerto","VBC","Valencia Basket","Guard",-2.7,0,7],["Clement","Frisch","KBA","Kosner Baskonia","Forward",2,0,8],["Marius","Grigonis","ZAL","Zalgiris Kaunas","Forward",12.1,0,9],
             ["Mouhamed","Faye","PBB","Paris Basketball","Center",19.8,0,10],["Ibon","Navarro","CZV","Crvena Zvezda","Head Coach",25,0,11]]
        out["best"] = {"pos": 1, "team": "CSP Lausanne", "coach": "Thomas Bourlon", "md": 211.2, "tot": 1417.7,
                       "players": [{"first": a, "last": b, "club": c, "club_name": cn, "pos": po, "pts": pt, "cap": bool(cp), "slot": sl} for a, b, c, cn, po, pt, cp, sl in P]}
        return out
    if not token or not prev: return out
    try:
        rnd = _get(f"/tournaments/{TOURNAMENT}/standings?matchday={prev['id']}", token)["data"]
        try:
            tot = _get(f"/tournaments/{TOURNAMENT}/standings", token)["data"]
        except Exception:
            tot = rnd
        tot = sorted(tot, key=lambda x: -(x.get("total_pts") or 0))
        row = lambda x: {"pos": x.get("position"), "team": x["name"], "coach": f'{x["user"]["first_name"]} {x["user"]["last_name"]}'.strip(),
                         "md": x.get("matchday_pts"), "tot": x.get("total_pts")}
        out["overall"] = [dict(row(x), pos=i + 1) for i, x in enumerate(tot[:10])]
        rnd = sorted(rnd, key=lambda x: -(x.get("matchday_pts") or 0))
        out["round_top"] = [dict(row(x), pos=i + 1) for i, x in enumerate(rnd[:3])]
        b = rnd[0]
        ro = _get(f"/fantasy-teams/{b['id']}/matchdays/{prev['id']}/roster/preview", token)["data"]
        pl = sorted(ro["players"], key=lambda p: p.get("court_position") or 99)
        out["best"] = dict(row(b), players=[{"first": p["first_name"], "last": p["last_name"], "club": p["team"]["abbreviation"],
                                            "club_name": p["team"]["name"], "pos": p["position"]["name"], "pts": p.get("pts") or 0,
                                            "cap": bool(p.get("is_captain")), "slot": p.get("court_position")} for p in pl])
        out["n_teams"] = len(tot) if len(tot) > 25 else None
    except Exception as e:
        print("::warning::championnat fantasy illisible (jeton expiré ?) :", str(e)[:200])
    return out

if __name__ == "__main__":
    print(json.dumps(fetch(), ensure_ascii=False, indent=1)[:3000])
