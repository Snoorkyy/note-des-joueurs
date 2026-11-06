"""Notation EuroLeague France — moteur v1 (0-10)."""
import re
from collections import defaultdict

# ---------- Paramètres ----------
W_ACTION = {  # valeur de chaque action (évaluation pondérée)
    "2": 2, "3": 3, "1": 1,          # points marqués
    "x": -1, "y": -1, "z": -1,       # tir / LF raté
    "O": 1.5, "D": 1,                # rebond OFF valorisé
    "A": 1, "S": 1, "B": 1,          # passe, interception, contre
    "T": -1.5,                       # balle perdue pénalisée
    "G": -1,                         # contré
    "F": -1, "f": -1,                # fautes commises (antisportive/technique exclues, comme le box officiel)
    "R": 1,                          # faute provoquée
}
def w_margin(m):              # poids selon l'écart AVANT l'action
    m = abs(m)
    if m <= 5:  return 1.20
    if m <= 10: return 1.00
    if m <= 15: return 0.70
    return 0.40
K_MIN   = 0.45   # production attendue par minute
K_RENT  = 0.5    # poids rentabilité au tir
TS_REF  = 0.57   # TS% de référence EuroLeague
K_PM    = 0.35   # poids du +/- contextuel
SCALE   = 8.0    # points bruts par point de note
WIN     = 0.5    # bonus victoire / malus défaite
MIN_MIN = 4.0

TOK = re.compile(r"^(\d+)([A-Za-z0-9])([a-z_])([AB])(?:(\d+)-(\d+))?$")

def parse(txt, code2id):
    ev, q = [], 0
    for t in txt.split():
        if t.startswith("#"): q = int(t[1:]); continue
        m = TOK.match(t)
        if not m: continue
        s, typ, pc, team, pa, pb = m.groups()
        ev.append(dict(q=q, s=int(s), typ=typ, pid=code2id.get(pc), team=team,
                       sa=int(pa) if pa else None, sb=int(pb) if pb else None))
    return ev

def run(box, pbp_txt, codes, final):
    code2id = {v: k for k, v in codes.items()}
    ev = parse(pbp_txt, code2id)
    on = {"A": set(), "B": set()}
    for pid, r in box.items():
        if r["st"]: on[r["team"]].add(pid)
    sa = sb = 0
    eval_ctx = defaultdict(float); eval_raw = defaultdict(float)
    pm_ctx = defaultdict(float); pm_raw = defaultdict(int)
    for e in ev:
        pid, typ = e["pid"], e["typ"]
        if typ == "I" and pid: on[e["team"]].add(pid); continue
        if typ == "U" and pid: on[e["team"]].discard(pid); continue
        w = w_margin(sa - sb)
        if pid and typ in W_ACTION:
            eval_ctx[pid] += W_ACTION[typ] * w
            eval_raw[pid] += W_ACTION[typ]
        if e["sa"] is not None:
            da, db = e["sa"] - sa, e["sb"] - sb
            pts = da - db  # du point de vue A
            for p in on["A"]: pm_ctx[p] += pts * w; pm_raw[p] += pts
            for p in on["B"]: pm_ctx[p] -= pts * w; pm_raw[p] -= pts
            sa, sb = e["sa"], e["sb"]
    res = []
    for pid, r in box.items():
        if r["min"] < MIN_MIN: continue
        cible = r["pir"] + 0.5 * r["orb"] - 0.5 * r["to"]
        ecart = cible - eval_raw[pid]
        if abs(ecart) > 1e-9:
            eval_ctx[pid] += ecart; eval_raw[pid] += ecart
        tsa = r["a2"] + r["a3"] + 0.44 * r["fta"]
        rent = r["pts"] - 2 * TS_REF * tsa
        attendu = K_MIN * r["min"]
        brut = eval_ctx[pid] + K_RENT * rent + K_PM * pm_ctx[pid] - attendu
        won = final[r["team"]] > final["B" if r["team"] == "A" else "A"]
        note = 5 + brut / SCALE + (WIN if won else -WIN)
        note = max(0, min(10, note))
        res.append(dict(r, eval_plus=eval_raw[pid], eval_ctx=eval_ctx[pid], rent=rent,
                        pm_chk=pm_raw[pid], pm_ctx=pm_ctx[pid], attendu=attendu,
                        brut=brut, note=round(note * 2) / 2, note_exacte=note))
    return sorted(res, key=lambda x: -x["note_exacte"])
