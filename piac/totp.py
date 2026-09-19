# -*- coding: utf-8 -*-
"""totp.py — TOTP (RFC 6238) + MS Authenticator-kompatibilis otpauth:// link.

Miért saját: nincs pyotp a rendszeren, és a TOTP maga ~20 sor stdlib
(hmac + hashlib + base64). Így a service bármelyik Pythonból fut.

MS Authenticator / Google Authenticator / Authy kompatibilis:
  otpauth://totp/<kiadó>:<fiók>?secret=<BASE32>&issuer=<kiadó>&algorithm=SHA1&digits=6&period=30
"""
import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
import urllib.parse

# ── a titok tárolása ──────────────────────────────────────────────────────
_ITT = os.path.dirname(os.path.abspath(__file__))
_TOTP_FAJL = os.path.join(_ITT, "totp.json")


def _betolt():
    import json
    if not os.path.exists(_TOTP_FAJL):
        return {}
    try:
        with open(_TOTP_FAJL, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _ment(d):
    import json
    tmp = _TOTP_FAJL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _TOTP_FAJL)
    try:
        os.chmod(_TOTP_FAJL, 0o600)
    except Exception:
        pass


# ── a titok (base32, ahogy az Authenticatorok várják) ──────────────────────
def titok_keszit(nev="ferenc"):
    """Új 20 bájtos (160 bit) titok — base32-ben, MS Authenticator-formátum."""
    nyers = secrets.token_bytes(20)
    b32 = base64.b32encode(nyers).decode("ascii").rstrip("=")
    d = _betolt()
    d["titok"] = b32
    d["nev"] = nev
    d["letrehozva"] = time.time()
    _ment(d)
    return b32


def titok():
    """A meglévő titok, vagy újat készít."""
    d = _betolt()
    if d.get("titok"):
        return d["titok"]
    return titok_keszit(d.get("nev") or "ferenc")


def otpauth_link(kiado="Piaci Ar-elemzo", fiok="ferenc"):
    """Az otpauth:// link, amit az Authenticator beolvas."""
    t = titok()
    cimke = urllib.parse.quote("%s:%s" % (kiado, fiok))
    return ("otpauth://totp/%s?secret=%s&issuer=%s"
            "&algorithm=SHA1&digits=6&period=30"
            % (cimke, t, urllib.parse.quote(kiado)))


# ── a kód számítása (RFC 6238) ────────────────────────────────────────────
def _b32_nyers(b32):
    """base32 -> bájtok (a hiányzó '=' pótlásával)."""
    b32 = b32.strip().upper().replace(" ", "")
    b32 += "=" * ((8 - len(b32) % 8) % 8)
    return base64.b32decode(b32)


def kod(idobelyeg=None, lepes=30, hossz=6, titok_b32=None):
    """A 6 jegyű TOTP kód az adott időpontra (alap: most)."""
    t = titok_b32 or titok()
    mp = int(idobelyeg if idobelyeg is not None else time.time())
    szamlalo = mp // lepes
    uzenet = struct.pack(">Q", szamlalo)
    kulcs = _b32_nyers(t)
    lenyomat = hmac.new(kulcs, uzenet, hashlib.sha1).digest()
    eltolas = lenyomat[-1] & 0x0F
    resz = struct.unpack(">I", lenyomat[eltolas:eltolas + 4])[0] & 0x7FFFFFFF
    return str(resz % (10 ** hossz)).zfill(hossz)


def hatralevo():
    """Hány másodpercig érvényes a mostani kód (a 30 mp-es ablakból)."""
    return 30 - int(time.time()) % 30


def ellenoriz(beirt, tures=1):
    """A beírt kód ellenőrzése. tures=1: az előző/aktuális/következő ablak is jó
    (óra-eltérés és a beírás ideje miatt — ez az iparági gyakorlat)."""
    if not beirt:
        return False
    beirt = str(beirt).strip().replace(" ", "")
    if not beirt.isdigit() or len(beirt) != 6:
        return False
    most = time.time()
    for i in range(-tures, tures + 1):
        if hmac.compare_digest(kod(most + i * 30), beirt):
            return True
    return False


if __name__ == "__main__":
    # önteszt: RFC 6238 hivatalos tesztvektorai
    RFC_TITOK = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"   # "12345678901234567890"
    vektorok = [
        (59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
        (1234567890, "89005924"), (2000000000, "69279037"),
    ]
    print("=== RFC 6238 önteszt (SHA1, 8 jegy) ===")
    ok = True
    for mp, vart in vektorok:
        kapott = kod(mp, hossz=8, titok_b32=RFC_TITOK)
        jo = kapott == vart
        ok = ok and jo
        print("  %-12s várt: %s  kapott: %s  %s" % (mp, vart, kapott, "✓" if jo else "✗"))
    print()
    print("  ÖSSZESEN: %s" % ("MINDEN HELYES — a TOTP motor korrekt ✓" if ok else "HIBA ✗"))
    print()
    print("=== az élő link ===")
    print("  %s" % otpauth_link()[:80] + "...")
    print("  mostani kód: %s (%d mp múlva vált)" % (kod(), hatralevo()))
