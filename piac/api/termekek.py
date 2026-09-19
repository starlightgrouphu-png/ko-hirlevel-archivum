# -*- coding: utf-8 -*-
"""api/termekek.py — Vercel serverless: terméklista + kategória-bontás.

Kategória-tudatos: a termékek a saját kategóriájuk piaci sávjához mérhetők,
SOHA nem egy globális átlaghoz (ŐÜA 09-19: ez volt az első verzió hibája).
"""
import json
import os
from http.server import BaseHTTPRequestHandler

ADAT = os.path.join(os.path.dirname(__file__), "_adat", "jelentes.json")


def _b():
    try:
        with open(ADAT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        d = _b()
        if d is None:
            return self._v(503, {"hiba": "nincs adat", "ok": False})
        kat = d.get("kategoriak", {}) or {}
        lista = []
        for nev, v in sorted(kat.items()):
            v = v or {}
            lista.append({
                "kategoria": nev,
                "sajat_db": v.get("sajat", 0),
                "piac_db": v.get("piac_n", 0),
                "piac_min": v.get("piac_min"),
                "piac_median": v.get("piac_median"),
                "piac_max": v.get("piac_max"),
            })
        ossz = sum(k["sajat_db"] for k in lista)
        self._v(200, {
            "ok": True,
            "termekek_szam": ossz,
            "kategoriak": lista,
            "utolso_meres": d.get("ido") or d.get("utolso_meres"),
        })

    def _v(self, kod, obj):
        n = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(n)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(n)
