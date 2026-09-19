# -*- coding: utf-8 -*-
"""api/kpi.py — Vercel serverless: KPI (BaseHTTPRequestHandler)."""
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
        kat = d.get("kategoriak", {})
        self._v(200, {
            "ok": True,
            "sajat_termek": d.get("sajat_termek_szam", 0),
            "konkurens": d.get("konkurens_ar_szam", 0),
            "konkurens_ar": d.get("konkurens_ar_szam", 0),
            "kategoriak_szam": len(kat),
            "utolso_meres": d.get("ido"),
            "parosult": 0, "olcsobb": 0, "dragabb": 0,
        })

    def _v(self, kod, obj):
        n = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(n)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(n)
