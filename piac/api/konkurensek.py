# -*- coding: utf-8 -*-
"""api/konkurensek.py — Vercel serverless: piaci sávok (BaseHTTPRequestHandler)."""
import json
import os
from http.server import BaseHTTPRequestHandler

ADAT = os.path.join(os.path.dirname(__file__), "_adat", "jelentes.json")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            with open(ADAT, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            return self._v(503, {"hiba": "nincs adat", "ok": False})
        self._v(200, {"ok": True, "konkurensek": [],
                      "kategoriak": d.get("kategoriak", {})})

    def _v(self, kod, obj):
        n = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(n)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(n)
