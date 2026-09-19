# BELÉPÉS — ELRAKTÁROZVA (2026-09-19, Ferenc kérésére)

**Státusz:** ⏸️ FÉLBEHAGYVA — Ferenc kérésére. „Most nem ez a lényeg, majd később folytatjuk."

## Hol tartottunk (mind kész és bizonyított)

### 1. QR-belépés (kamera) — KÉSZ ✅
- A gép megnyitja: `http://<cím>:8100/belepes`
- Megjelenik a QR + **90 mp-es visszaszámláló** (csík + „lejár: X mp")
- Lejárat után pirosra vált + megjelenik a **„↻ Új QR-kód kérése"** gomb
- A telefon **kamerájával** beolvasva → a telefon jelez → a **gép** erősíti meg → a gép belép

### 2. TOTP (MS Authenticator) — KÉSZ ✅
- A lapon egy második QR: `otpauth://totp/...` — ezt az **Authenticator** olvassa
- Onnantól 30 mp-enként mutat egy 6 jegyű kódot; a gépen beírva belépés
- **RFC 6238 összes hivatalos tesztvektora átment** → az Authenticator elfogadja

### 3. Jelszó — KÉSZ ✅
- A régi űrlap él; rossz jelszó → 401

### 4. Biztonsági javítások (2×ÖÜA + 2×ÖÜAEF) — KÉSZ ✅
| Hiba | Állapot |
|---|---|
| K1: `/qr/megerosit` auth nélkül bárkinek belépést adott | ✅ javítva — gép-titok, a telefon csak jelez |
| `qr_atalakit` dupla definíció (a gyenge élt) | ✅ javítva |
| H1: `/eszkoz/torol` belépés nélkül | ✅ 401 |
| H2: QR újrafelhasználás (TOCTOU) | ✅ atomi |
| H2b: idegen Host a QR-linkben | ✅ 400 |
| H3: `_QR` zár nélkül | ✅ Lock |
| H4: brute-force | ✅ 429 |

## 🔴 A LEGFONTOSABB TANULSÁG (miért nem működött az Authenticator)

```
A qr_svg.py a segno könyvtárat hívta, DE:
  segno.save(StringIO)  ->  TypeError (byte-okat ír szövegbe)
  -> a try/except CSENDBEN elnyelte
  -> a TARTALÉK saját rajzoló futott
  -> ÉRVÉNYTELEN QR-t rajzolt
  -> SE az Authenticator, SE a kamera nem tudta beolvasni!

JAVÍTÁS: BytesIO (a segno byte-okat ír) -> helyes QR
```
**Ellenőrzés MINDIG dekódolóval (OpenCV), SOHA szemmel/vision-modell-lal!**

## Fájlok
- `szerver.py` — végpontok + IP/Host-kapu
- `auth.py` — QR-állapotgép, eszköz-token, jelszó
- `totp.py` — TOTP motor (RFC 6238) + otpauth link
- `belepo_lap.py` — a belépő oldal (számláló + gomb + TOTP blokk)
- `qr_svg.py` — QR-generálás (segno, BytesIO-val)

## Mi van hátra, ha folytatjuk
- [ ] A belépés visszakapcsolása (a kód él, csak ki van kapcsolva)
- [ ] Esetleg: több felhasználó (most egyetlen közös fiók: `ferenc`)
- [ ] Esetleg: az eszközök listája/törlése a felületen (`/eszkozok` él)
- [ ] A QR-ek PNG-exportja megvan: `/qr/kep?kod=X` és `/totp/kep`

## Hogyan kapcsoljuk vissza (1 lépés)
A `szerver.py`-ben a `_BELEPES_KELL = False` → `True`, majd:
`systemctl --user restart piac-platform`
