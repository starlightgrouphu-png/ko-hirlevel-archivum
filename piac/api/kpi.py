# -*- coding: utf-8 -*-
"""api/kpi.py — Vercel serverless: KPI (BaseHTTPRequestHandler).

Az adat a Windows-natív szinkronból érkezik: api/_adat/jelentes.json
FAIL-CLOSED: ha nincs adat, 503-at ad — SOHA nem hazudik.
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
        # a saját termékszám: a gyökér-mező, vagy a kategóriák összege
        sajat = d.get("sajat_termek")
        if not sajat:
            sajat = sum((v or {}).get("sajat", 0) for v in kat.values())
        # a konkurens árak száma
        konk = d.get("konkurens_ar")
        if not konk:
            konk = sum((v or {}).get("piac_n", 0) for v in kat.values())
        self._v(200, {
            "ok": True,
            "sajat_termek": sajat,
            "konkurens": konk,
            "konkurens_ar": konk,
            "kategoriak_szam": len(kat),
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
