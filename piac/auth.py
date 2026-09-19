#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auth.py — belépési kapu: JELSZÓ + QR-KÓD + ESZKÖZ-EMLÉKEZÉS.

Ferenc 2026-09-19 (TARTÓS):
  "QR kóddal és mobil telefon segítségével szeretnék ide belépni, és
   jegyezze meg a gépet, ahonnan beléptem, és egy bizonyos ideig ne
   kelljen újra belépni."

HÁROM ÚT (mind él egymás mellett):
  1. JELSZÓ      — a data/auth.json-ban (PBKDF2-HMAC-SHA256, 200 000 kör, só)
  2. QR-KÓD      — a gép képernyőjén megjelenik a QR; a telefon beolvassa
                   -> a telefon oldala megerősíti -> a GÉP böngészője belép
                   (a QR 90 mp-ig él, egyszer használható)
  3. ESZKÖZ-TOKEN — a böngésző tárolja (HttpOnly süti); 90 napig nem kér
                   jelszót. A token HMAC-elt, a jelszó-hash-ből származik,
                   így jelszó-csere esetén minden eszköz-token érvénytelen.

0 LLM-token, stdlib-only.
"""
import hashlib
import threading
import hmac
import json
import os
import secrets
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# a szerver BASE/auth.json-t használ — ugyanaz
AUTH_FAJL = os.path.join(HERE, "auth.json")
KOROK = 200_000
SUTI_NEV = "piac_kapu"
SUTI_KOR = 7 * 24 * 3600            # a munkamenet-süti (7 nap)
ESZKOZ_NEV = "piac_eszkoz"
ESZKOZ_KOR = 90 * 24 * 3600         # 90 nap — Ferenc döntése (09-19)
QR_KOR = 90                         # a QR-kód 90 másodpercig él

# a függő QR-kérések (memóriában; a szerver egyszerre fut)
_QR = {}
_ZAR = threading.Lock()      # H3: versenyhelyzet ellen (ThreadingHTTPServer)


# ── alap ────────────────────────────────────────────────────────────────────
def _betolt():
    try:
        with open(AUTH_FAJL, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    # a szerver-formátum (dashboard/admin) és a saját formátum (so/hash) együtt
    if "eszkozok" not in d:
        d["eszkozok"] = {}
    return d


def _ment(d):
    os.makedirs(os.path.dirname(AUTH_FAJL), exist_ok=True)
    tmp = AUTH_FAJL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f)
    os.replace(tmp, AUTH_FAJL)
    try:
        os.chmod(AUTH_FAJL, 0o600)
    except Exception:
        pass


def van_jelszo():
    return bool(_betolt().get("hash"))


def jelszo_beallit(uj):
    so = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", uj.encode(), bytes.fromhex(so), KOROK).hex()
    d = _betolt()
    d.update({"so": so, "hash": h, "beallitva": time.time(), "eszkozok": {}})
    _ment(d)


def jelszo_ellenoriz(probalt):
    d = _betolt()
    if not d.get("hash"):
        return False
    h = hashlib.pbkdf2_hmac("sha256", probalt.encode(),
                            bytes.fromhex(d["so"]), KOROK).hex()
    return hmac.compare_digest(h, d["hash"])


# ── süti-aláírás (a jelszó-hash-ből származtatott kulccsal) ─────────────────
def _kulcs():
    d = _betolt()
    if not d.get("hash"):
        return b""
    return hashlib.sha256(("suti:" + d["hash"]).encode()).digest()


def suti_keszit(felhasznalo="ferenc"):
    lejar = int(time.time()) + SUTI_KOR
    uzenet = "%s|%d" % (felhasznalo, lejar)
    alair = hmac.new(_kulcs(), uzenet.encode(), hashlib.sha256).hexdigest()[:32]
    return "%s|%d|%s" % (felhasznalo, lejar, alair)


def suti_ervenyes(suti):
    if not suti:
        return False
    try:
        felh, lejar, alair = suti.split("|")
        lejar = int(lejar)
    except Exception:
        return False
    if lejar < time.time():
        return False
    vart = hmac.new(_kulcs(), ("%s|%d" % (felh, lejar)).encode(),
                    hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(vart, alair)


# ── 2) ESZKÖZ-TOKEN (90 nap) ────────────────────────────────────────────────
def _eszkoz_kulcs():
    d = _betolt()
    if not d.get("hash"):
        return b""
    return hashlib.sha256(("eszkoz:" + d["hash"]).encode()).digest()


def eszkoz_keszit(nev="", ua=""):
    """Új eszköz-token. A nevet/UA-t eltárolja (ki melyik gép)."""
    tok = secrets.token_urlsafe(24)
    tid = hashlib.sha256(tok.encode()).hexdigest()[:16]
    d = _betolt()
    d.setdefault("eszkozok", {})[tid] = {
        "nev": (nev or "ismeretlen")[:60],
        "ua": (ua or "")[:120],
        "letrehozva": int(time.time()),
        "lejar": int(time.time()) + ESZKOZ_KOR,
        "utolso": int(time.time()),
    }
    _ment(d)
    alair = hmac.new(_eszkoz_kulcs(), tok.encode(), hashlib.sha256).hexdigest()[:32]
    return "%s.%s" % (tok, alair)


def eszkoz_ervenyes(ertek):
    """Az eszköz-token ellenőrzése + a 'utolso latott' frissítése."""
    if not ertek or "." not in ertek:
        return False
    tok, _, alair = ertek.rpartition(".")
    vart = hmac.new(_eszkoz_kulcs(), tok.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(vart, alair):
        return False
    tid = hashlib.sha256(tok.encode()).hexdigest()[:16]
    d = _betolt()
    e = (d.get("eszkozok") or {}).get(tid)
    if not e:
        return False
    if int(e.get("lejar") or 0) < time.time():
        d["eszkozok"].pop(tid, None)
        _ment(d)
        return False
    e["utolso"] = int(time.time())
    _ment(d)
    return True


def eszkozok_lista():
    d = _betolt()
    most = time.time()
    ki = []
    for tid, e in (d.get("eszkozok") or {}).items():
        ki.append({
            "id": tid,
            "nev": e.get("nev"),
            "letrehozva": e.get("letrehozva"),
            "lejar": e.get("lejar"),
            "hatralevo_nap": max(0, int((int(e.get("lejar") or 0) - most) / 86400)),
            "utolso": e.get("utolso"),
        })
    return sorted(ki, key=lambda x: -(x.get("utolso") or 0))


def eszkoz_torol(tid):
    d = _betolt()
    if tid in (d.get("eszkozok") or {}):
        d["eszkozok"].pop(tid)
        _ment(d)
        return True
    return False


def sutik_fejlec(suti, torles=False, eszkoz=None):
    """A munkamenet- és az eszköz-süti együtt."""
    fej = []
    if torles:
        fej.append("Set-Cookie: %s=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" % SUTI_NEV)
        fej.append("Set-Cookie: %s=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" % ESZKOZ_NEV)
        return fej
    fej.append("Set-Cookie: %s=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax"
               % (SUTI_NEV, suti, SUTI_KOR))
    if eszkoz:
        fej.append("Set-Cookie: %s=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax"
                   % (ESZKOZ_NEV, eszkoz, ESZKOZ_KOR))
    return fej


# ── 3) QR-KÓD (a gép képernyőjén -> telefon beolvassa -> a gép belép) ───────
def qr_indit(gep_nev=""):
    """Új QR-kérés. A gép böngészője hívja; a token 90 mp-ig él."""
    kod = secrets.token_urlsafe(16)
    _QR[kod] = {"letrehozva": time.time(), "allapot": "var", "gep": (gep_nev or "")[:40]}
    return kod


def qr_ervenyes(kod):
    e = _QR.get(kod)
    if not e:
        return False
    if time.time() - e["letrehozva"] > QR_KOR:
        _QR.pop(kod, None)
        return False
    return True


def qr_megerosit(kod):
    """A telefon hívja (a QR-ban lévő linket megnyitva) -> a gép belép.
    H2/H3: zár alatt, és rögzíti a megerősítés idejét (lejárat-ellenőrzéshez)."""
    with _ZAR:
        a = _QR.get(kod)
        if not a or time.time() - a.get("letrehozva", 0) > 300:
            return False
        a["allapot"] = "megerositve"
        a["megerositve_ido"] = time.time()
        _QR[kod] = a
        return True


def qr_atalakit(kod):
    """H2: ATOMIVAN 'megerositve' -> 'belepve' (csak egyszer lephet be vele)."""
    with _ZAR:
        if not qr_ervenyes(kod):
            return False
        e = _QR.get(kod)
        if not e or e["allapot"] != "megerositve":
            return False
        e["allapot"] = "belepve"
        return True


def qr_allapot(kod):
    """A gép böngészője pollozza: var / megerositve / lejart."""
    if not qr_ervenyes(kod):
        return "lejart"
    return _QR[kod]["allapot"]


def qr_felold(kod):
    """Egyszer használatos: a belépés után töröljük."""
    _QR.pop(kod, None)


def qr_atalakit(kod):
    """H2: ATOMI átalakítás 'megerősítve' -> 'felhasználva'.
    True: ez a hívás nyerte meg (ő kaphat sütit). False: más már elhasználta.
    A zár miatt két szál egyszerre NEM kaphat belépést ugyanarra a kódra."""
    with _ZAR:
        a = _QR.get(kod)
        if not a or a.get("allapot") != "megerositve":
            return False
        # 30 mp-nél régebbi megerősítés ne legyen érvényes (friss belépés kell)
        if time.time() - a.get("megerositve_ido", 0) > 300:
            _QR.pop(kod, None)
            return False
        a["allapot"] = "felhasznalva"
        _QR[kod] = a
        return True


def qr_takarit():
    """A lejárt QR-kérések törlése."""
    most = time.time()
    for k in [k for k, v in _QR.items() if most - v["letrehozva"] > QR_KOR]:
        _QR.pop(k, None)


# ── a szerver-oldali kapu ───────────────────────────────────────────────────
VEDETT_KIVETEL = ("/api/ping", "/belepes", "/qr", "/static/", "/favicon", "/egeszseg")


def keres_vedett(ut):
    return not any(ut == k or ut.startswith(k) for k in VEDETT_KIVETEL)


def sutik_olvas(fejlecek):
    """A kérés fejlécéből a sütik."""
    kapu, eszkoz = None, None
    for k, v in fejlecek.items():
        if k.lower() == "cookie":
            for darab in v.split(";"):
                if "=" in darab:
                    nev, _, ertek = darab.strip().partition("=")
                    if nev == SUTI_NEV:
                        kapu = ertek
                    elif nev == ESZKOZ_NEV:
                        eszkoz = ertek
    return kapu, eszkoz


def belepes_lap(hiba=False, qr_kod=None):
    """A belépő oldal: jelszó + QR-kód (a QR a gépen jelenik meg)."""
    hibauzenet = ("<p class='hiba'>Hibás jelszó.</p>" if hiba else "")
    qr_blokk = ""
    if qr_kod:
        qr_blokk = """
  <div class="qr">
    <p>Vagy: olvasd be a telefont!</p>
    <img src="/qr/kep?kod=__KOD__" alt="QR-kód" width="200" height="200">
    <p class="kicsi">A telefon beolvassa, és ez a gép belép.</p>
  </div>
  <script>/* QR-POLL-BEKOTVE */
  (function(){
    var kod = "__KOD__";
    var n = 0;
    var id = setInterval(function(){
      n++;
      if (n > 180) { clearInterval(id); return; }   // 90 mp utan feladja
      fetch("/qr/allapot?kod=" + kod).then(function(r){ return r.json(); })
        .then(function(d){
          if (d.allapot === "megerositve") {
            clearInterval(id);
            window.location.href = "/qr/belepes?kod=" + kod;
          }
        }).catch(function(){});
    }, 1500);
  })();
  </script>""".replace("__KOD__", qr_kod)
    lap = """<!doctype html><html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Belépés — Piaci Ár-elemző</title>
<style>
 body{background:#0f1117;color:#e6e6e6;font-family:system-ui,sans-serif;
      display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
 .doboz{background:#1a1d27;padding:2rem;border-radius:12px;width:320px;text-align:center}
 h1{font-size:1.2rem;margin:0 0 .3rem}
 p{color:#9aa;font-size:.85rem}
 input{width:100%;padding:.7rem;margin:.8rem 0;border-radius:8px;border:1px solid #333;
       background:#0f1117;color:#fff;box-sizing:border-box}
 button{width:100%;padding:.7rem;border:0;border-radius:8px;background:#3b82f6;
        color:#fff;font-weight:600;cursor:pointer}
 .hiba{color:#f87171}
 .qr{margin-top:1.5rem;border-top:1px solid #333;padding-top:1rem}
 .kicsi{font-size:.72rem;color:#667}
</style></head><body>
<div class="doboz">
  <h1>Piaci Ár-elemző</h1>
  <p>Kockaország + MiniDreams</p>
  __HIBA__
  <form method="post" action="/belepes">
    <input type="password" name="jelszo" placeholder="Jelszó" autofocus autocomplete="current-password">
    <button type="submit">Belépés</button>
  </form>
  __QR__
</div></body></html>"""
    return lap.replace("__HIBA__", hibauzenet).replace("__QR__", qr_blokk)
