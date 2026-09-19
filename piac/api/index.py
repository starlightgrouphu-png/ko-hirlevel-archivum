# -*- coding: utf-8 -*-
"""api/index.py — Vercel serverless (BaseHTTPRequestHandler szabvány).

A Vercel Python-függvénye egy HTTP-kezelőt vár (nem `handler(request)`-et).
Ez a függvény a PUBLIKUS, előre kiszámolt adatot szolgálja ki.

Adatforrás: api/_adat/jelentes.json (a Windows-natív szinkron tölti fel)
FAIL-CLOSED: ha nincs adat, 503-at ad — SOHA nem hazudik.
"""
import json
import os
from http.server import BaseHTTPRequestHandler

ADAT = os.path.join(os.path.dirname(__file__), "_adat", "jelentes.json")


def _betolt():
    try:
        with open(ADAT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        d = _betolt()
        if d is None:
            self._valasz(503, {"hiba": "nincs feltöltött adat", "ok": False})
            return
        self._valasz(200, {"ok": True, "adat": d})

    def _valasz(self, kod, obj):
        nyers = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(nyers)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(nyers)
