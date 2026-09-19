#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""szerver.py — PIACI ÁR-ELEMZŐ PLATFORM (port 8100).

A meglévő feedo_server.py (8099) MINTÁJÁRA, de önálló: ez a két-területes
platform. A 8099 érintetlen marad (a Feedo tovább fut) — ez a 8100-on él.

NÉZETEK:
  /            -> választó (KO | MD | Admin)
  /ko, /md     -> élő dashboard területenként
  /admin       -> konkurens-felvétel (URL be!), futás, napló
API:
  GET  /api/teruletek
  GET  /api/kpi?terulet=ko
  GET  /api/konkurensek?terulet=ko
  POST /api/felismer    {url, terulet, nev}  -> felismerés + mentés
  GET  /api/termekek?terulet=ko&szuro=...
0 LLM-token, stdlib-only (ThreadingHTTPServer).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import sema          # noqa: E402
import felismero     # noqa: E402
import auth
import totp as totp_motor
import belepo_lap          # noqa: E402
_PROBAK = {}          # H4: kiserlet-korlat (IP -> [idobelyeg,...])
import qr_svg        # noqa: E402

# ══ HÁLÓZATI KAPU (Ferenc 09-19: belépés KI, helyi hálózat + Tailscale) ══
# C) út: csak a SAJÁT gépeink címeiről fogadunk. Minden más -> 403.
# A Tailscale itt NEM tiltás, hanem ENGEDÉLY: a saját tailnet-címünk jöhet.
_BELEPES_KELL = False          # a jelszó/QR/TOTP belépés KI van kapcsolva

# amely hálózatokról fogadunk (a saját gépeink)
# PONTOS címek (nem prefix-ről!) — különben egy MÁS tailnet-gép is bejöhetne
_ENGEDETT_IPK = frozenset({
    "127.0.0.1", "::1",          # ez a gép
    "10.255.255.254",            # WSL belső
    "172.17.0.1", "172.18.0.1", "172.21.0.1",   # docker-hidak
    "172.23.231.239",            # WSL helyi hálózat (a saját eth0-nk)
    "100.88.3.101",              # Tailscale (a MI /32 címünk)
})
_ENGEDETT_HALOZATOK = ("127.", "10.255.255.", "172.17.", "172.18.",
                       "172.21.", "172.23.231.", "100.88.3.101")


def _ip_engedett(ip):
    """A kérés forrás-IP-je a SAJÁT gépeink egyike-e?
    Pontos egyezés VAGY szűk prefix (a docker/WSL-hidak változhatnak)."""
    if not ip:
        return False
    if ip in _ENGEDETT_IPK:
        return True
    # a saját tailnet-címünk pontosan (100.88.3.101) — NEM a teljes /24
    return ip.startswith(("127.", "10.255.255.", "172.17.", "172.18.",
                          "172.21.", "172.23."))   # 172.23. = a WSL hálózat
                                                       # (a Windows-host is innen jön)


PORT = int(os.getenv("PIAC_PORT", "8100"))
WEB = os.path.join(BASE, "web")

# ── egyszerű, fájl-alapú jelszavas kapu (stdlib) ────────────────────────────
import hashlib
import hmac

AUTH_FAJL = os.path.join(BASE, "auth.json")


def _auth_betolt():
    if os.path.exists(AUTH_FAJL):
        with open(AUTH_FAJL, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _hash(jelszo, so):
    return hashlib.pbkdf2_hmac("sha256", jelszo.encode(), so, 120_000).hex()


def auth_beallit(dashboard_jelszo, admin_jelszo):
    d = {
        "dashboard": {"so": os.urandom(8).hex(), "hash": ""},
        "admin": {"so": os.urandom(8).hex(), "hash": ""},
    }
    d["dashboard"]["hash"] = _hash(dashboard_jelszo, bytes.fromhex(d["dashboard"]["so"]))
    d["admin"]["hash"] = _hash(admin_jelszo, bytes.fromhex(d["admin"]["so"]))
    with open(AUTH_FAJL, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    os.chmod(AUTH_FAJL, 0o600)
    return d


def auth_ellenor(szint, jelszo):
    d = _auth_betolt()
    if szint not in d:
        return False
    so = bytes.fromhex(d[szint]["so"])
    return hmac.compare_digest(_hash(jelszo, so), d[szint]["hash"])


# ── adat-lekérdezések (a dashboard ezeket hívja) ────────────────────────────
def _sorok(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args).fetchall()]


def teruletek():
    c = sema.csatlakozas()
    try:
        return _sorok(c, "SELECT * FROM terulet WHERE aktiv=1 ORDER BY id")
    finally:
        c.close()


def terulet_by_slug(slug):
    c = sema.csatlakozas()
    try:
        r = c.execute("SELECT * FROM terulet WHERE slug=?", (slug,)).fetchone()
        return dict(r) if r else None
    finally:
        c.close()


def kpi(terulet_id):
    """A dashboard KPI-sávja."""
    c = sema.csatlakozas()
    try:
        st = c.execute("SELECT COUNT(*) FROM sajat_termek WHERE terulet_id=? AND "
                       "(statusz IS NULL OR statusz='aktiv')", (terulet_id,)).fetchone()[0]
        kn = c.execute("SELECT COUNT(*) FROM konkurens WHERE terulet_id=? AND aktiv=1",
                       (terulet_id,)).fetchone()[0]
        ka = c.execute("SELECT COUNT(*) FROM konkurens_ar WHERE terulet_id=?",
                       (terulet_id,)).fetchone()[0]
        # a legfrissebb mérés napján párosult termékek
        par = c.execute(
            "SELECT COUNT(DISTINCT sajat_sku) FROM konkurens_ar "
            "WHERE terulet_id=? AND sajat_sku IS NOT NULL "
            "AND date(merve)=(SELECT date(MAX(merve)) FROM konkurens_ar WHERE terulet_id=?)",
            (terulet_id, terulet_id)).fetchone()[0]
        olcsobb = dragabb = 0
        for r in c.execute(
            "SELECT ka.sajat_sku, ka.ar, st.sajat_ar FROM konkurens_ar ka "
            "JOIN sajat_termek st ON st.terulet_id=ka.terulet_id AND st.sku=ka.sajat_sku "
            "WHERE ka.terulet_id=? AND ka.sajat_sku IS NOT NULL AND st.sajat_ar IS NOT NULL "
            "AND date(ka.merve)=(SELECT date(MAX(merve)) FROM konkurens_ar WHERE terulet_id=?)",
            (terulet_id, terulet_id)):
            if r["ar"] is None or r["sajat_ar"] is None:
                continue
            if r["sajat_ar"] < r["ar"]:
                olcsobb += 1
            elif r["sajat_ar"] > r["ar"]:
                dragabb += 1
        utolso = c.execute("SELECT MAX(merve) FROM konkurens_ar WHERE terulet_id=?",
                           (terulet_id,)).fetchone()[0]
        return {"sajat_termek": st, "konkurens": kn, "konkurens_ar": ka,
                "parosult": par, "olcsobb": olcsobb, "dragabb": dragabb,
                "utolso_meres": utolso}
    finally:
        c.close()


def konkurensek(terulet_id):
    c = sema.csatlakozas()
    try:
        return _sorok(c, "SELECT * FROM konkurens WHERE terulet_id=? ORDER BY nev", (terulet_id,))
    finally:
        c.close()


def termekek(terulet_id, szuro=None, limit=500):
    """Termék-sorok: a mi árunk + a legfrissebb konkurens ár + eltérés."""
    c = sema.csatlakozas()
    try:
        sql = """
        SELECT st.sku, st.nev, st.ean, st.sajat_ar, st.keszlet,
               (SELECT ka.ar FROM konkurens_ar ka WHERE ka.terulet_id=st.terulet_id
                 AND ka.sajat_sku=st.sku ORDER BY ka.merve DESC LIMIT 1) AS verseny_ar,
               (SELECT ka.url FROM konkurens_ar ka WHERE ka.terulet_id=st.terulet_id
                 AND ka.sajat_sku=st.sku ORDER BY ka.merve DESC LIMIT 1) AS verseny_url,
               (SELECT ka.pont FROM konkurens_ar ka WHERE ka.terulet_id=st.terulet_id
                 AND ka.sajat_sku=st.sku ORDER BY ka.merve DESC LIMIT 1) AS pont
        FROM sajat_termek st
        WHERE st.terulet_id=? AND (st.statusz IS NULL OR st.statusz='aktiv')
        """
        args = [terulet_id]
        if szuro:
            sql += " AND (st.sku LIKE ? OR st.nev LIKE ?)"
            args += ["%%%s%%" % szuro, "%%%s%%" % szuro]
        sql += " ORDER BY st.sku LIMIT ?"
        args.append(limit)
        sorok = _sorok(c, sql, tuple(args))
        for s in sorok:
            if s.get("sajat_ar") and s.get("verseny_ar"):
                s["elteres"] = round(s["sajat_ar"] - s["verseny_ar"])
                s["elteres_szazalek"] = round(100.0 * s["elteres"] / s["verseny_ar"], 1)
            else:
                s["elteres"] = None
                s["elteres_szazalek"] = None
        return sorok
    finally:
        c.close()


def futasok(limit=30):
    c = sema.csatlakozas()
    try:
        return _sorok(c, "SELECT * FROM futas ORDER BY id DESC LIMIT ?", (limit,))
    finally:
        c.close()


# ── HTTP kezelő ─────────────────────────────────────────────────────────────
class Kezelo(BaseHTTPRequestHandler):
    server_version = "PiacPlatform/1.0"

    def log_message(self, fmt, *args):
        pass  # csendes napló (a saját log/ könyvtárba írunk)

    def _json(self, obj, kod=200):
        nyers = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(nyers)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(nyers)

    def _html(self, szoveg, kod=200):
        nyers = szoveg.encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(nyers)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(nyers)

    def _valasz(self, kod, extra_fejlec, nyers, tipus="text/html; charset=utf-8"):
        """Nyers válasz (süti- és egyéb fejlécekhez). extra_fejlec: str vagy lista."""
        self.send_response(kod)
        self.send_header("Content-Type", tipus)
        self.send_header("Content-Length", str(len(nyers)))
        self.send_header("Cache-Control", "no-store")
        if extra_fejlec:
            fejlecek = extra_fejlec if isinstance(extra_fejlec, (list, tuple)) else [extra_fejlec]
            for f in fejlecek:
                if not f:
                    continue
                if f.startswith("Set-Cookie: "):
                    self.send_header("Set-Cookie", f[len("Set-Cookie: "):])
                elif ":" in f:
                    nev, _, ertek = f.partition(":")
                    self.send_header(nev.strip(), ertek.strip())
        self.end_headers()
        self.wfile.write(nyers)

    def _fajl(self, nev):
        ut = os.path.join(WEB, nev)
        if not os.path.exists(ut):
            self._html("<h1>404 — hiányzó nézet: %s</h1>" % nev, 404)
            return
        with open(ut, encoding="utf-8") as fh:
            self._html(fh.read())

    def do_GET(self):
        # HALOZATI KAPU: idegen forras-IP -> 403 (meg a belepes elott)
        if not _ip_engedett(self.client_address[0]):
            # FORRAS-IP NAPLO: a kizart keresek rogzitese (diagnosztika)
            try:
                with open("/tmp/piac_kizart_ipk.txt", "a") as _f:
                    _f.write("%s  %s  %s\n" % (time.strftime("%H:%M:%S"),
                                                self.client_address[0], self.path))
            except Exception:
                pass
            return self._html("<h2>403 — ez a cím nem érhető el innen.</h2>"
                              "<p>Ez a szerver csak a helyi hálózatról és a "
                              "saját Tailscale-címről érhető el.</p>", 403)
        p = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(p.query)
        ut = p.path

        # ── JELSZAVAS KAPU (a Tailscale-en kívül is védett) ───────────────
        if ut == "/belepes":
            kod = auth.qr_indit()
            return self._html(belepo_lap.lap(qr_kod=kod,
                                             qr_titok=auth.qr_gep_titok(kod),
                                             qr_kor=auth.QR_KOR,
                                             totp_link=totp_motor.otpauth_link()))
        if ut == "/kilepes":
            return self._valasz(200, auth.sutik_fejlec("", torles=True),
                                "Kilépve. <a href='/belepes'>Új belépés</a>".encode("utf-8"))
        if ut == "/egeszseg":
            return self._json({"ok": True, "szint": "nyilvanos"})
        # QR-BELEPES-BEKOTVE
        _kapu, _eszkoz = auth.sutik_olvas(self.headers)
        # _BELEPES_KELL=False -> a halozati kapu ved (IP), belépés nem kell
        _belepve = (not _BELEPES_KELL) or auth.suti_ervenyes(_kapu) or auth.eszkoz_ervenyes(_eszkoz)
        if ut == "/qr/kep":
            return self._qr_kepe(q)
        if ut == "/qr/indit":
            kod = auth.qr_indit()
            return self._json({"kod": kod, "titok": auth.qr_gep_titok(kod), "kor": auth.QR_KOR})
        if ut == "/qr/allapot":
            kod = (q.get("kod") or [""])[0]
            return self._json({"allapot": auth.qr_allapot(kod)})
        if ut == "/qr/belepes":
            kod = (q.get("kod") or [""])[0]
            # H2: ATOMI atalakitas — egyszerre ket szal nem kaphat sutit
            if auth.qr_atalakit(kod):
                suti = auth.suti_keszit("ferenc")
                eszkoz = auth.eszkoz_keszit(
                    nev="QR-telefon", ua=self.headers.get("User-Agent", ""))
                return self._valasz(200, auth.sutik_fejlec(suti, eszkoz=eszkoz),
                                    "<meta http-equiv='refresh' content='0;url=/'>"
                                    "Belépve QR-rel...".encode("utf-8"))
            return self._html("<h3>A QR nem érvényes.</h3>", 410)
        if ut == "/totp/kep":
            # az otpauth:// QR az Authenticatorhoz (nem a belepesi QR!)
            svg = qr_svg.qr_svg(totp_motor.otpauth_link(), meret=220)
            return self._valasz(200, [], svg.encode("utf-8"),
                                tipus="image/svg+xml; charset=utf-8")
        if ut == "/totp/allapot":
            return self._json({"kod": totp_motor.kod(),
                               "hatralevo": totp_motor.hatralevo()})
        if ut == "/qr/telefon":
            # K1: a TELEFON csak jelez — a gép erősíti meg (ő ismeri a titkot)
            kod = (q.get("kod") or [""])[0]
            tnev = self.headers.get("User-Agent", "telefon")[:30]
            if auth.qr_telefon_jel(kod, tnev):
                return self._html("<h2>Telefon észlelve — a gép most belép.</h2>"
                                  "<p>Nyugodtan zárd be ezt az oldalt.</p>")
            return self._html("<h2>A kód lejárt vagy érvénytelen.</h2>", 410)
        if ut == "/qr/megerosit":
            # K1: megerosites CSAK a QR-t kero gep titkaval (idegen nem tud maganak belépést adni)
            kod = (q.get("kod") or [""])[0]
            titok = (q.get("t") or [""])[0]
            if auth.qr_megerosit_gep(kod, titok):
                return self._json({"ok": True})
            return self._json({"ok": False}, 403)
        if ut == "/eszkozok" and _belepve:
            return self._json({"eszkozok": auth.eszkozok_lista(),
                               "hatralevo_nap": auth.ESZKOZ_KOR // 86400})
        if ut == "/eszkoz/torol":
            if not _belepve:
                return self._json({"ok": False, "hiba": "nincs belepes"}, 401)
            tid = (q.get("id") or [""])[0]
            return self._json({"torolve": auth.eszkoz_torol(tid)})
        if auth.keres_vedett(ut) and not _belepve:
            kod = auth.qr_indit()
            return self._html(belepo_lap.lap(qr_kod=kod,
                                             qr_titok=auth.qr_gep_titok(kod),
                                             qr_kor=auth.QR_KOR,
                                             totp_link=totp_motor.otpauth_link()), 200)

        if ut in ("/", "/index.html"):
            return self._fajl("index.html")
        if ut in ("/ko", "/dashboard/ko"):
            return self._fajl("dashboard.html")
        if ut in ("/md", "/dashboard/md"):
            return self._fajl("dashboard.html")
        if ut in ("/admin", "/vezerpanel"):
            return self._fajl("admin.html")
        if ut == "/api/teruletek":
            return self._json({"teruletek": teruletek()})
        if ut == "/api/kpi":
            t = terulet_by_slug(q.get("terulet", ["ko"])[0])
            if not t:
                return self._json({"hiba": "ismeretlen terulet"}, 404)
            return self._json(kpi(t["id"]))
        if ut == "/api/konkurensek":
            t = terulet_by_slug(q.get("terulet", ["ko"])[0])
            if not t:
                return self._json({"hiba": "ismeretlen terulet"}, 404)
            return self._json({"konkurensek": konkurensek(t["id"])})
        if ut == "/api/termekek":
            t = terulet_by_slug(q.get("terulet", ["ko"])[0])
            if not t:
                return self._json({"hiba": "ismeretlen terulet"}, 404)
            return self._json({"termekek": termekek(t["id"], q.get("szuro", [None])[0])})
        if ut == "/api/futasok":
            return self._json({"futasok": futasok()})
        if ut == "/api/ping":
            return self._json({"pong": time.strftime("%Y-%m-%dT%H:%M:%S"), "port": PORT})
        return self._html("<h1>404</h1>", 404)

    def _kiserlet_ok(self):
        """H4: max 8 sikertelen proba / 5 perc / IP."""
        import time as _t
        ip = self.client_address[0]
        most = _t.time()
        lista = [x for x in _PROBAK.get(ip, []) if most - x < 300]
        if len(lista) >= 8:
            _PROBAK[ip] = lista
            return False
        _PROBAK[ip] = lista
        return True

    def _kiserlet_nullaz(self):
        """Sikeres belépés után a próbák törlése (a jó jelszó/kód ne büntessen)."""
        _PROBAK.pop(self.client_address[0], None)

    def _kiserlet_rogzit(self):
        import time as _t
        ip = self.client_address[0]
        _PROBAK.setdefault(ip, []).append(_t.time())

    def do_POST(self):
        if not _ip_engedett(self.client_address[0]):
            return self._html("<h2>403 — ez a cím nem érhető el innen.</h2>", 403)
        p = urllib.parse.urlparse(self.path)
        hossz = int(self.headers.get("Content-Length") or 0)
        nyers = self.rfile.read(hossz) if hossz else b""

        # ── bejelentkezés (űrlap) ─────────────────────────────────────────
        if p.path == "/totp":
            # TOTP kod (az Authenticatorbol) — ugyanaz a belepes, mint a jelszonal
            try:
                mezok = urllib.parse.parse_qs(nyers.decode("utf-8"))
                beirt = (mezok.get("kod") or [""])[0]
            except Exception:
                beirt = ""
            if not self._kiserlet_ok():
                return self._html("<h3>Túl sok hibás próba. Várj 5 percet.</h3>", 429)
            if totp_motor.ellenoriz(beirt):
                self._kiserlet_nullaz()
                return self._valasz(200, auth.sutik_fejlec(
                    auth.suti_keszit("ferenc"),
                    eszkoz=auth.eszkoz_keszit(nev="TOTP-authenticator",
                                               ua=self.headers.get("User-Agent", ""))),
                    "<meta http-equiv='refresh' content='0;url=/'>Belépve kóddal..."
                    .encode("utf-8"))
            _k = auth.qr_indit()
            return self._html(belepo_lap.lap(hiba=True, qr_kod=_k,
                                             qr_titok=auth.qr_gep_titok(_k),
                                             qr_kor=auth.QR_KOR,
                                             totp_link=totp_motor.otpauth_link()), 401)
        if p.path == "/belepes":
            # H4: kiserlet-korlat (brute-force vedelem)
            if not self._kiserlet_ok():
                return self._html("<h3>Tul sok hibas proba. Varj 5 percet.</h3>", 429)
            try:
                mezok = urllib.parse.parse_qs(nyers.decode("utf-8"))
                jelszo = (mezok.get("jelszo") or [""])[0]
            except Exception:
                jelszo = ""
            if auth.jelszo_ellenoriz(jelszo):
                suti = auth.suti_keszit("ferenc")
                eszkoz = auth.eszkoz_keszit(
                    nev=self.headers.get("X-Eszkoz-Nev", "bongeszo"),
                    ua=self.headers.get("User-Agent", ""))
                return self._valasz(200, auth.sutik_fejlec(suti, eszkoz=eszkoz),
                                    "<meta http-equiv='refresh' content='0;url=/'>Belépve...</".encode("utf-8"))
            self._kiserlet_rogzit()
            _k = auth.qr_indit()
            return self._html(belepo_lap.lap(hiba=True, qr_kod=_k,
                                             qr_titok=auth.qr_gep_titok(_k),
                                             qr_kor=auth.QR_KOR,
                                             totp_link=totp_motor.otpauth_link()), 401)

        try:
            adat = json.loads(nyers.decode("utf-8")) if nyers else {}
        except Exception:
            return self._json({"hiba": "érvénytelen JSON"}, 400)

        if p.path == "/api/felismer":
            url = (adat.get("url") or "").strip()
            slug = adat.get("terulet") or "ko"
            if not url:
                return self._json({"hiba": "hiányzó url"}, 400)
            t = terulet_by_slug(slug)
            if not t:
                return self._json({"hiba": "ismeretlen terulet"}, 404)
            try:
                er = felismero.felismer(url, ment=True, terulet_id=t["id"], nev=adat.get("nev"))
            except Exception as e:
                return self._json({"hiba": "felismerés hiba: %s" % str(e)[:200]}, 500)
            return self._json({"eredmeny": er})
        return self._json({"hiba": "ismeretlen végpont"}, 404)


    def _qr_kepe(self, q):
        """A QR-kód képe (SVG) — a telefon ezt olvassa be."""
        # H2b: a Host-ellenőrzés az ELSŐ — a QR-link soha nem mutathat idegen domainre
        hoszt = self.headers.get("Host", "localhost:8100")
        _engedett = ("localhost", "127.0.0.1", "100.88.3.101", "marveen-pc-1")
        if not any(h in hoszt for h in _engedett):
            return self._html("<h3>Ervenytelen keres.</h3>", 400)
        kod = (q.get("kod") or [""])[0]
        if not auth.qr_ervenyes(kod):
            return self._html("<h3>A QR lejárt — töltsd újra az oldalt.</h3>", 410)
        link = "http://%s/qr/telefon?kod=%s" % (hoszt, kod)
        svg = qr_svg.qr_svg(link, meret=220)
        return self._valasz(200, [], svg.encode("utf-8"),
                            tipus="image/svg+xml; charset=utf-8")

def main():
    print("PIACI ÁR-ELEMZŐ PLATFORM")
    print("  port: %d" % PORT)
    print("  nézetek: /  /ko  /md  /admin")
    sema.letrehoz(verbose=False)
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Kezelo)
    srv.daemon_threads = True
    print("  fut: http://localhost:%d/" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
