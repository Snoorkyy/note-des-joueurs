"""Points marqués par joueur et par match (feuilles de match officielles EuroLeague) -> data.json["pts"] = {pid: {gamecode: points}}.
Sert aux jeux (grille, l'intrus, cartes de collection). Rattrape tous les matchs publiés qui manquent.
Usage : python3 robot/points.py
"""
import json, os, sys, time, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.json")
UA = {"User-Agent": "Mozilla/5.0 (EuroLeague France robot)"}

def box_points(season, code):
    for k in range(6):                       # le serveur limite le débit (429) : on patiente et on réessaie
        try:
            req = urllib.request.Request(f"https://live.euroleague.net/api/Boxscore?gamecode={code}&seasoncode={season}", headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                b = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or k == 5: raise
            time.sleep(10 * (k + 1))
    out = {}
    for s in b["Stats"]:
        for q in s["PlayersStats"]:
            pid = (q.get("Player_ID") or "").strip()
            if pid and ":" in (q.get("Minutes") or ""):
                out[pid] = int(q.get("Points") or 0)
    return out

def main():
    d = json.load(open(DATA, encoding="utf-8"))
    pts = d.setdefault("pts", {})
    done = {c for v in pts.values() for c in v}
    todo = []
    for m in d["matches"]:
        season, code = m["id"].split("-")
        if code not in done: todo.append((season, code))
    print("matchs à rattraper :", len(todo))
    n = 0
    for season, code in todo:
        try: bp = box_points(season, code)
        except Exception as e: print(code, "indisponible :", e); continue
        for pid, p in bp.items(): pts.setdefault(pid, {})[code] = p
        n += 1
        time.sleep(1.5)
    if n:
        json.dump(d, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("matchs ajoutés :", n)

if __name__ == "__main__":
    main()
