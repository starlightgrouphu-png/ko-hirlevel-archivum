#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nagyker_motor.py — NAGYKER + WEBSHOP árazási motor (több-boltos, állítható).

Ferenc 2026-09-19 (TARTÓS):
    "minden nagyker kapcsolatot egyenként viszünk fel a két webshophoz külön-külön,
     és az árazást, illetve minden egyéb adatot is lehessen állítani a jövőben,
     és definiálni a szabályokat külön-külön"

Ez a motor EZT valósítja meg:
  - a nagyker-forrást a cikkszám PREFIXE azonosítja (AGS, LD, EDU, STT, ...)
  - a szorzó nagykerenként állítható (nagyker_szorzok.json)
  - a webshop (MD/KO) saját árazási szabályt hordozhat
  - minden érték felülírható, a fájl szerkesztésével — kódmódosítás NÉLKÜL

A SZÁMÍTÁS (a hivatalos, Ferenc-megerősített képlet):
    alap   = eur × MNB × árfolyam_biztosítás × szorzó
    bruttó = ceil((alap − 90)/100)×100 + 90      (mindig …90-re végződik)
    nettó  = bruttó / 1,27                        (27% AFA)
    bruttó > 150 000 → NEM listázható (fail-closed)

FONTOS: ismeretlen prefix → a LEGALACSONYABB szorzó (óvatos árazás, fail-closed).
"""
import json
import math
import os
import re

ALAP_KONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nagyker_szorzok.json")

# a hivatalos bázisértékek (ha a konfig nem ad mást)
MNB_FALLBACK = 364.45
ARFOLYAM_BIZTOSITAS = 1.02
AFA = 1.27
MAX_BRUTTO = 150000


def _betolt(utvonal=None):
    """A konfiguráció betöltése. Hibánál None (fail-closed)."""
    try:
        with open(utvonal or ALAP_KONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def prefix_kinyer(sku):
    """A cikkszám prefixe — EZ azonosítja a nagyker-forrást.

    'AGS-10455-1' -> 'AGS' | 'LD7483' -> 'LD' | 'STT-001247274' -> 'STT'
    Az ismeretlen/üres esetén None.
    """
    if not sku:
        return None
    m = re.match(r"^([A-Za-z]{1,6})[-_ ]", str(sku))
    if not m:
        m = re.match(r"^([A-Za-z]{1,6})(?=\d)", str(sku))
    return m.group(1).upper() if m else None


def szorzo(sku, eur, konfig=None):
    """A nagykerhez (prefixhez) és EUR-árhoz tartozó szorzó.

    Visszaad: (szorzo, forras_nev, forras_kulcs)
    Ismeretlen prefixnél az alap (legalacsonyabb) szorzó — fail-closed.
    """
    k = konfig if konfig is not None else _betolt()
    if not k:
        return 1.75, "ismeretlen (konfig hiba)", None
    p = prefix_kinyer(sku)
    nagyker = (k.get("nagyker") or {}).get(p) if p else None
    if not nagyker:
        alap = k.get("_alap_ha_nincs_prefix") or {}
        return float(alap.get("szorzo_alatt", 1.75)), alap.get("nev", "ismeretlen"), p
    hatar = float(nagyker.get("hatar_eur", 10.0))
    if (eur or 0) < hatar:
        return float(nagyker.get("szorzo_alatt", 1.75)), nagyker.get("nev", p), p
    return float(nagyker.get("szorzo_felett", 1.85)), nagyker.get("nev", p), p


def kerek_90(alap):
    """Az ár mindig …90-re végződik."""
    return math.ceil((alap - 90) / 100.0) * 100 + 90


def ar_keplet(sku, eur, mnb=None, konfig=None):
    """A teljes számítás egy termékre.

    Visszaad dict-et: {brutto, netto, szorzo, forras, prefix, listazhato}
    FAIL-CLOSED: ha nincs EUR-ár vagy a bruttó > 150 000 → listazhato=False.
    """
    k = konfig if konfig is not None else _betolt()
    af  = float((k or {}).get("_arfolyam_biztositas", ARFOLYAM_BIZTOSITAS)) if k else ARFOLYAM_BIZTOSITAS
    afa = float((k or {}).get("_afa", AFA)) if k else AFA
    mx  = float((k or {}).get("_max_brutto", MAX_BRUTTO)) if k else MAX_BRUTTO
    if mnb is None:
        mnb = MNB_FALLBACK

    if not eur or eur <= 0:
        return {"ok": False, "hiba": "nincs EUR-ár", "brutto": 0, "netto": 0.0,
                "szorzo": 0.0, "forras": None, "prefix": prefix_kinyer(sku), "listazhato": False}

    sz, forras, pref = szorzo(sku, eur, k)
    alap = eur * mnb * af * sz
    brutto = kerek_90(alap)
    netto = round(brutto / afa, 2)
    return {
        "ok": True,
        "prefix": pref,
        "forras": forras,
        "szorzo": sz,
        "brutto": brutto,
        "netto": netto,
        "listazhato": brutto <= mx,
        "ok_ar": brutto > mx,
    }


def webshop_nagyker_szorzo(webshop, sku, eur, konfig=None):
    """Webshop-specifikus szorzó (MD/KO külön állítható).

    Ha a webshop ad saját szorzót a nagykerhez, azt használja; egyébként a közöst.
    """
    k = konfig if konfig is not None else _betolt()
    if not k:
        return szorzo(sku, eur, k)
    p = prefix_kinyer(sku)
    ws = (k.get("webshopok") or {}).get(webshop) or {}
    ws_sz = (ws.get("nagyker_szorzok") or {}).get(p)
    if ws_sz:
        hatar = float(ws_sz.get("hatar_eur", 10.0))
        if (eur or 0) < hatar:
            return float(ws_sz.get("szorzo_alatt", 1.75)), "%s/%s" % (webshop, p), p
        return float(ws_sz.get("szorzo_felett", 1.85)), "%s/%s" % (webshop, p), p
    return szorzo(sku, eur, k)


if __name__ == "__main__":
    # önteszt — bizonyíték, hogy a motor él
    print("=== NAGYKER-MOTOR ÖNTESZT ===")
    for sku, eur in [("AGS-10455-1", 15.0), ("LD7483", 25.0), ("EDU-CA150024", 5.0),
                     ("STT-001247274", 40.0), ("ISMERETLEN-123", 12.0)]:
        r = ar_keplet(sku, eur)
        print("  %-20s %5.1f EUR -> %8d Ft (netto %8.0f) | szorzó %.2f | %s" % (
            sku, eur, r["brutto"], r["netto"], r["szorzo"], r["forras"]))
