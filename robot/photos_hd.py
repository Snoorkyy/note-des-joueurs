"""Détourages officiels des joueurs (pour les cartes « FUT ») : photos-hd/<pid>.webp, 450 × 600, fond transparent.
Source : api-live.euroleague.net (images.headshot, 750 × 1000). Ne télécharge que les joueurs notés sans détourage
(ou tous avec --all). Usage : python3 robot/photos_hd.py [--all]"""
import io, json, os, sys, urllib.request
from PIL import Image
SEASON = "E2026"
def get(u, raw=False):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"}), timeout=40) as r:
        b = r.read(); return b if raw else json.loads(b.decode())
d = json.load(open("data.json", encoding="utf-8"))
want = {n[0] for n in d["notes"]}
os.makedirs("photos-hd", exist_ok=True)
j = get(f"https://api-live.euroleague.net/v2/competitions/E/seasons/{SEASON}/people?personType=J")
items = j.get("data", j) if isinstance(j, dict) else j
heads = {}
for x in items:
    u = (x.get("images") or {}).get("headshot")
    if u: heads["P" + str(x["person"]["code"]).zfill(6)] = u
ok = miss = 0
for p in sorted(want):
    f = f"photos-hd/{p}.webp"
    if os.path.exists(f) and "--all" not in sys.argv: continue
    u = heads.get(p)
    if not u: miss += 1; continue
    try:
        im = Image.open(io.BytesIO(get(u, True))).convert("RGBA")
        if im.getchannel("A").getextrema()[0] == 255: miss += 1; continue  # pas de détourage
        im = im.resize((450, int(450 * im.height / im.width)), Image.LANCZOS)
        im.save(f, "WEBP", quality=82, method=6); ok += 1
    except Exception as e:
        print(p, "erreur", e); miss += 1
# écussons des clubs en HD (logos-hd/<code>.webp, 256 px, fond transparent)
os.makedirs("logos-hd", exist_ok=True)
try:
    cj = get(f"https://api-live.euroleague.net/v2/competitions/E/seasons/{SEASON}/clubs")
    for x in (cj.get("data", cj) if isinstance(cj, dict) else cj):
        code, u = x.get("code"), (x.get("images") or {}).get("crest")
        if not code or not u or code not in d["clubs"]: continue
        f = f"logos-hd/{code}.webp"
        if os.path.exists(f) and "--all" not in sys.argv: continue
        try:
            im = Image.open(io.BytesIO(get(u, True))).convert("RGBA"); im = im.crop(im.getchannel("A").getbbox() or (0, 0, im.width, im.height))
            k = 256 / max(im.size); im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
            im.save(f, "WEBP", quality=88, method=6); print("écusson", code)
        except Exception as e: print("écusson", code, "erreur", e)
except Exception as e:
    print("écussons indisponibles :", e)
have = sorted(x[:-5] for x in os.listdir("photos-hd") if x.endswith(".webp"))
json.dump(have, open("photos-hd/index.json", "w"), separators=(",", ":"))
print(f"{ok} détourages ajoutés, {miss} sans détourage, {len(have)} au total")
