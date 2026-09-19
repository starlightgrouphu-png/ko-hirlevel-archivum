# -*- coding: utf-8 -*-
"""belepo_lap.py — a belépő oldal (jelszó + QR számlálóval + TOTP az Authenticatorhoz).

Három út, bármelyikkel be lehet lépni:
  1) JELSZÓ        — a meglévő űrlap
  2) QR (kamera)   — a telefon kamerájával beolvasva; visszaszámláló mutatja,
                     meddig él; lejárat után egy gomb új QR-t kér
  3) TOTP kód      — az MS Authenticator mutat 6 jegyet, azt a gépen beírva

A QR és a TOTP KÜLÖN dolog:
  - a QR egy sima HTTP-link (kamera/QR-olvasó nyitja meg)  -> a telefon JELEZ
  - a TOTP egy otpauth:// titok (Authenticator olvassa)    -> 6 jegyű kód
"""
import html
import json

STILUS = """
 body{background:#0f1117;color:#e6e6e6;font-family:system-ui,-apple-system,sans-serif;
      display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:1rem}
 .doboz{background:#1a1d27;padding:1.6rem;border-radius:14px;width:360px;
        box-shadow:0 8px 32px rgba(0,0,0,.5)}
 h1{font-size:1.15rem;margin:0 0 .2rem}
 h2{font-size:.85rem;margin:1.2rem 0 .5rem;color:#9aa;font-weight:600;
    text-transform:uppercase;letter-spacing:.05em}
 p{color:#9aa;font-size:.8rem;margin:.4rem 0}
 input{width:100%;padding:.7rem;margin:.5rem 0;border-radius:8px;border:1px solid #333;
       background:#0f1117;color:#fff;box-sizing:border-box;font-size:1rem}
 button{width:100%;padding:.7rem;border:0;border-radius:8px;background:#3b82f6;
        color:#fff;font-weight:600;cursor:pointer;font-size:.95rem}
 button:hover{background:#2563eb}
 button.kis{padding:.45rem;font-size:.8rem;background:#2a2f3e;margin-top:.5rem}
 button.kis:hover{background:#3b4358}
 .hiba{color:#f87171;font-size:.85rem;text-align:center}
 .qr{text-align:center;margin-top:1rem;padding-top:1rem;border-top:1px solid #2a2f3e}
 .qr img{background:#fff;padding:8px;border-radius:10px;display:block;margin:0 auto}
 .kicsi{font-size:.72rem;color:#667}
 .elv{position:relative;width:200px;height:5px;background:#2a2f3e;border-radius:3px;
      margin:.6rem auto;overflow:hidden}
 .elv span{position:absolute;left:0;top:0;height:100%;background:#3b82f6;
           border-radius:3px;transition:width .9s linear}
 .elv.lejart span{background:#ef4444}
 .szam{font-variant-numeric:tabular-nums;font-weight:600;color:#9aa}
 .totp-kod{font-size:1.7rem;letter-spacing:.35rem;font-variant-numeric:tabular-nums;
           font-weight:700;color:#60a5fa;text-align:center;margin:.5rem 0}
 .zold{color:#4ade80}
 .sarga{color:#fbbf24}
 button:disabled{background:#2a2f3e;color:#556;cursor:not-allowed}
"""


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def lap(hiba=False, qr_kod=None, qr_titok=None, qr_kor=90, totp_link=None, totp_kod=None):
    """A teljes belépő oldal."""
    hibauzenet = "<p class='hiba'>Hibás jelszó.</p>" if hiba else ""

    # ── QR blokk (számlálóval és újragenerálás gombbal) ──────────────────
    qr_blokk = ""
    if qr_kod:
        qr_blokk = """
  <div class="qr">
    <h2>Vagy: QR a telefonnal</h2>
    <img id="qrkep" src="/qr/kep?kod=__KOD__" alt="QR-kód" width="200" height="200">
    <div class="elv" id="elv"><span id="elvcsik" style="width:100%%"></span></div>
    <p class="szam">lejár: <span id="mp">__KOR__</span> mp</p>
    <p class="kicsi">A telefon <b>kamerájával</b> olvasd be — ez a gép belép.</p>
    <button type="button" class="kis" id="ujgomb" style="display:none"
            onclick="ujQr()">&#8635; Új QR-kód kérése</button>
  </div>
  <script>/* QR-POLL (K1: a gep erositi meg) */
  (function(){
    var kod = "__KOD__", titok = "__TITOK__", kor = __KOR__;
    var hatralevo = kor, megerositve = false, lejart = false, ciklus = null;

    var elv = document.getElementById("elv");
    var csik = document.getElementById("elvcsik");
    var mp = document.getElementById("mp");
    var gomb = document.getElementById("ujgomb");

    function frissit(){
      hatralevo--;
      if (hatralevo < 0) hatralevo = 0;
      mp.textContent = hatralevo;
      csik.style.width = (100 * hatralevo / kor) + "%";
      if (hatralevo <= 0 && !megerositve) {
        lejart = true;
        elv.classList.add("lejart");
        gomb.style.display = "block";
        mp.textContent = "lejárt";
        if (ciklus) { clearInterval(ciklus); ciklus = null; }
      }
    }

    ciklus = setInterval(function(){
      if (lejart || megerositve) return;
      frissit();
      fetch("/qr/allapot?kod=" + kod).then(function(r){ return r.json(); })
        .then(function(d){
          if (d.allapot === "telefon_latta" && !megerositve) {
            megerositve = true;
            fetch("/qr/megerosit?kod=" + kod + "&t=" + encodeURIComponent(titok))
              .then(function(r){ return r.json(); }).catch(function(){});
          }
          if (d.allapot === "megerositve") {
            if (ciklus) clearInterval(ciklus);
            window.location.href = "/qr/belepes?kod=" + kod;
          }
        }).catch(function(){});
    }, 1000);

    window.ujQr = function(){ window.location.reload(); };
  })();
  </script>"""
        qr_blokk = (qr_blokk.replace("__KOD__", _esc(qr_kod))
                    .replace("__TITOK__", _esc(qr_titok or ""))
                    .replace("__KOR__", str(int(qr_kor))))

    # ── TOTP blokk (az Authenticatorhoz) ─────────────────────────────────
    totp_blokk = ""
    if totp_link:
        totp_blokk = """
  <div class="qr">
    <h2>Vagy: kód az Authenticatorból</h2>
    <img src="/totp/kep" alt="Authenticator QR" width="170" height="170">
    <p class="kicsi">Olvasd be az <b>Microsoft Authenticator</b>ral
       (vagy Google/Steam — bármelyikkel). Ezután 30 mp-enként mutat egy
       6 jegyű kódot; azt írd be ide:</p>
    <div class="totp-kod" id="mostkod">______</div>
    <p class="kicsi">(ez a mostani kód — <span id="totpmp">30</span> mp múlva vált)</p>
    <form method="post" action="/totp">
      <input type="text" name="kod" placeholder="6 jegyű kód" inputmode="numeric"
             autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}">
      <button type="submit">Belépés kóddal</button>
    </form>
  </div>
  <script>
  (function(){
    var id = setInterval(function(){
      fetch("/totp/allapot").then(function(r){ return r.json(); })
        .then(function(d){
          var e = document.getElementById("mostkod");
          if (e) e.textContent = d.kod;
          var m = document.getElementById("totpmp");
          if (m) m.textContent = d.hatralevo;
        }).catch(function(){});
    }, 1000);
  })();
  </script>"""

    return """<!doctype html><html lang="hu"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Belépés — Piaci Ár-elemző</title>
<style>__STILUS__</style></head><body>
<div class="doboz">
  <h1>Piaci Ár-elemző</h1>
  <p>Kockaország + MiniDreams</p>
  __HIBA__
  <form method="post" action="/belepes">
    <input type="password" name="jelszo" placeholder="Jelszó" autofocus
           autocomplete="current-password">
    <button type="submit">Belépés jelszóval</button>
  </form>
  __QR__
  __TOTP__
</div></body></html>""".replace("__STILUS__", STILUS) \
        .replace("__HIBA__", hibauzenet) \
        .replace("__QR__", qr_blokk) \
        .replace("__TOTP__", totp_blokk)
