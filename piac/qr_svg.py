#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qr_svg.py — QR-kód SVG-ben.

Ferenc 09-19: "QR kóddal és mobil telefon segítségével szeretnék belépni."

ELSŐDLEGES: a `segno` könyvtár (bizonyított, ISO/IEC 18004) — a gépen
            a .venv-qr venv-ben él.
TARTALÉK:   a saját, stdlib-only rajzoló (ha a segno nem elérhető),
            hogy a rendszer SOHA ne álljon meg egy hiányzó csomag miatt.

FONTOS: a .venv-qr egy KÜLÖN venv, ezért a szerver indításakor a
        sys.path-ba tesszük a site-packages-ét (lásd szerver.py).
"""
import os
import sys

# a .venv-qr site-packages a path-ra (ha van)
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, ".venv-qr", "lib", "python3.11", "site-packages"),
           os.path.join(_HERE, ".venv-qr", "lib", "python3.12", "site-packages")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import segno
    _VAN_SEGNO = True
except Exception:
    segno = None
    _VAN_SEGNO = False


def honnan():
    """Honnan jön a QR (átláthatósághoz)."""
    return "segno" if _VAN_SEGNO else "sajat-rajzolo"


def qr_svg(szoveg, meret=200, margo=4):
    """A QR-kód SVG-ként (a telefon kamerája beolvassa)."""
    if _VAN_SEGNO:
        try:
            q = segno.make(szoveg, error="m")
            from io import StringIO
            out = StringIO()
            q.save(out, kind="svg", scale=1, border=margo, dark="#000", light="#fff")
            svg = out.getvalue()
            # a méretet a meret-re igazítjuk (viewBox marad)
            if "viewBox" in svg:
                import re
                m = re.search(r'viewBox="([^"]+)"', svg)
                if m:
                    x, y, w, h = m.group(1).split()
                    svg = re.sub(r'<svg([^>]*?)width="[^"]*"', r'<svg\1width="%d"' % meret, svg, count=1)
                    svg = re.sub(r'<svg([^>]*?)height="[^"]*"', r'<svg\1height="%d"' % meret, svg, count=1)
            return svg
        except Exception:
            pass
    # TARTALÉK: a saját rajzoló (stdlib-only)
    return _sajat_qr_svg(szoveg, meret, margo)


# ── TARTALÉK: saját, stdlib-only QR-rajzoló ─────────────────────────────────
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gf_mul(a, b):
    return 0 if (a == 0 or b == 0) else _EXP[_LOG[a] + _LOG[b]]


def _rs_oszlop(adat, hossz):
    gen = [1]
    for i in range(hossz):
        uj = [0] * (len(gen) + 1)
        for j, c in enumerate(gen):
            uj[j] ^= _gf_mul(c, 1)
            uj[j + 1] ^= _gf_mul(c, _EXP[i])
        gen = uj
    maradek = list(adat) + [0] * hossz
    for i in range(len(adat)):
        e = maradek[i]
        if e != 0:
            for j, c in enumerate(gen):
                maradek[i + j] ^= _gf_mul(c, e)
    return maradek[len(adat):]


_VERZIOK = {1: (19, 7, 1), 2: (34, 10, 1), 3: (55, 15, 1), 4: (80, 20, 1),
            5: (108, 26, 1), 6: (136, 18, 2), 7: (156, 20, 2), 8: (194, 24, 2),
            9: (232, 30, 2), 10: (274, 18, 2)}


def _sajat_qr_svg(szoveg, meret=200, margo=4):
    adat = szoveg.encode("utf-8")
    v = None
    for k in sorted(_VERZIOK):
        hb = 8 if k <= 9 else 16
        if 4 + hb + len(adat) * 8 <= _VERZIOK[k][0] * 8:
            v = k
            break
    if v is None:
        raise ValueError("túl hosszú szöveg")
    hb = 8 if v <= 9 else 16
    bitek = [0, 1, 0, 0]
    for i in range(hb - 1, -1, -1):
        bitek.append((len(adat) >> i) & 1)
    for b in adat:
        for i in range(7, -1, -1):
            bitek.append((b >> i) & 1)
    kap = _VERZIOK[v][0] * 8
    for _ in range(min(4, kap - len(bitek))):
        bitek.append(0)
    while len(bitek) % 8:
        bitek.append(0)
    ksz = []
    for i in range(0, len(bitek), 8):
        b = 0
        for j in range(8):
            b = (b << 1) | bitek[i + j]
        ksz.append(b)
    while len(ksz) < _VERZIOK[v][0]:
        ksz.append(0xEC if len(ksz) % 2 == 0 else 0x11)
    ossz_adat, ec, blokk = _VERZIOK[v]
    if blokk == 1:
        vegso = ksz + _rs_oszlop(ksz, ec)
    else:
        per = ossz_adat // blokk
        ad, ecs = [], []
        for i in range(blokk):
            bl = ksz[i * per:(i + 1) * per]
            ad.append(bl)
            ecs.append(_rs_oszlop(bl, ec))
        vegso = []
        for i in range(per):
            for b in ad:
                if i < len(b):
                    vegso.append(b[i])
        for i in range(ec):
            for b in ecs:
                if i < len(b):
                    vegso.append(b[i])
    n = 17 + 4 * v
    m = [[None] * n for _ in range(n)]

    def kereso(sr, osz):
        for i in range(-1, 8):
            for j in range(-1, 8):
                r, c = sr + i, osz + j
                if 0 <= r < n and 0 <= c < n:
                    belso = (0 <= i <= 6 and 0 <= j <= 6)
                    szel = (i in (0, 6) or j in (0, 6))
                    koz = (2 <= i <= 4 and 2 <= j <= 4)
                    m[r][c] = 1 if (belso and (szel or koz)) else 0

    kereso(0, 0)
    kereso(0, n - 7)
    kereso(n - 7, 0)
    for i in range(8, n - 8):
        m[6][i] = 1 if i % 2 == 0 else 0
        m[i][6] = 1 if i % 2 == 0 else 0
    m[n - 8][8] = 1
    fi = [1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1, 0, 0]
    idx = 0
    for i in range(9):
        if i != 6:
            m[8][i] = fi[idx]
            idx += 1
    for i in range(n - 8, n):
        m[8][i] = fi[idx] if idx < len(fi) else 0
        idx += 1
    idx = 0
    for i in range(n - 1, n - 9, -1):
        if i != 6:
            m[i][8] = fi[idx] if idx < len(fi) else 0
            idx += 1
    for i in range(7, -1, -1):
        m[i][8] = fi[idx] if idx < len(fi) else 0
        idx += 1
    bitf = []
    for b in vegso:
        for i in range(7, -1, -1):
            bitf.append((b >> i) & 1)
    bi, felfele, oszlop = 0, True, n - 1
    while oszlop > 0:
        if oszlop == 6:
            oszlop -= 1
        for i in range(n):
            sor = (n - 1 - i) if felfele else i
            for c in (oszlop, oszlop - 1):
                if m[sor][c] is None:
                    bit = bitf[bi] if bi < len(bitf) else 0
                    bi += 1
                    if (sor + c) % 2 == 0:
                        bit ^= 1
                    m[sor][c] = bit
        felfele = not felfele
        oszlop -= 2
    teljes = n + 2 * margo
    egyseg = meret / teljes
    utak = []
    for r in range(n):
        for c in range(n):
            if m[r][c]:
                utak.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f"/>'
                            % ((c + margo) * egyseg, (r + margo) * egyseg,
                               egyseg + 0.02, egyseg + 0.02))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d"><rect width="100%%" height="100%%" fill="#fff"/>'
            '<g fill="#000">%s</g></svg>'
            % (meret, meret, meret, meret, "".join(utak)))
