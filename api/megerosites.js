// api/megerosites.js — KO hírlevél re-opt-in megerősítő végpont (Vercel serverless)
// A levél CTA gombja ide érkezik:  /api/megerosites?e=<email>
// Feladat: a MailerLite-on a feliratkozót unconfirmed -> active állítani,
//          majd a kupont megjeleníteni.
//
// BIZTONSÁG:
//   - state-changing GET, ezért a levélből érkező link közvetlenül használható
//   - egyszer használható: ha már active, nem hívunk API-t (idempotens)
//   - a MailerLite kulcs CSAK a Vercel env-ből (MAILERLITE_API_KEY)
//
// Vercel env beállítás:  vercel env add MAILERLITE_API_KEY

const ML_BASE = 'https://connect.mailerlite.com/api';

// egyszerű in-memory idempotencia (a hideg indítás újratölti — elég a védelemhez)
const marMegerositve = new Map();

function oldal({ cim, szin, torzs, kupon }) {
  return `<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${cim} — Kockaország hírlevél</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       font:16px/1.5 system-ui,'Segoe UI',Arial,sans-serif;background:#f4f6fb;color:#20243a;padding:24px}
  .kartya{background:#fff;border-radius:16px;padding:36px 30px;max-width:560px;width:100%;
          box-shadow:0 10px 40px rgba(32,29,85,.10);text-align:center}
  h1{margin:0 0 14px;font-size:26px;color:${szin}}
  p{margin:0 0 14px;color:#4a4f63}
  .kupon{background:#201D55;color:#fff;border-radius:12px;padding:20px;margin:18px 0}
  .kupon .kod{font-size:30px;font-weight:800;letter-spacing:3px}
  .kupon .felirat{font-size:12px;letter-spacing:2px;opacity:.75;margin-bottom:8px}
  .gomb{display:inline-block;margin-top:10px;background:#201D55;color:#fff;text-decoration:none;
        padding:14px 30px;border-radius:8px;font-weight:700}
  .lab{font-size:13px;color:#7c8299;margin-top:18px}
</style>
</head>
<body>
  <div class="kartya">
    <h1>${cim}</h1>
    ${torzs}
    ${kupon ? `<div class="kupon"><div class="felirat">A KUPONKÓDOD</div><div class="kod">${kupon}</div></div>` : ''}
    <a class="gomb" href="https://kockaorszag.hu">Irány a webshop →</a>
    <p class="lab">Kockaország · info@kockaorszag.hu · <a href="https://kockaorszag.hu">www.kockaorszag.hu</a></p>
  </div>
</body>
</html>`;
}

export default async function handler(req, res) {
  const email = (req.query.e || '').toString().trim().toLowerCase();

  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');

  if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    res.status(400).send(oldal({
      cim: 'Hiányos link', szin: '#d9534f',
      torzs: '<p>A megerősítő link hiányos. Kérjük, a levélben lévő gombra kattints.</p>'
    }));
    return;
  }

  // idempotencia: ugyanaz a cím egyszer
  if (marMegerositve.get(email)) {
    res.status(200).send(oldal({
      cim: 'Már meg van erősítve ✅', szin: '#2e9e5b',
      torzs: '<p>A feliratkozásod már aktív — nincs több teendőd.</p>',
      kupon: 'UDVOZOL5'
    }));
    return;
  }

  const kulcs = process.env.MAILERLITE_API_KEY;
  if (!kulcs) {
    res.status(500).send(oldal({
      cim: 'Átmeneti hiba', szin: '#d9534f',
      torzs: '<p>A rendszer átmenetileg nem elérhető. Kérjük, próbáld meg később.</p>'
    }));
    return;
  }

  try {
    // 1) jelenlegi állapot
    const getu = await fetch(
      `${ML_BASE}/subscribers/${encodeURIComponent(email)}`,
      { headers: { Accept: 'application/json', Authorization: `Bearer ${kulcs}` } }
    );

    if (getu.status === 404) {
      res.status(200).send(oldal({
        cim: 'Nem találjuk a feliratkozást', szin: '#e08b00',
        torzs: '<p>Ezzel a címmel nem találunk feliratkozást. Kérjük, iratkozz fel újra a weboldalunkon.</p>'
      }));
      return;
    }
    if (!getu.ok) {
      res.status(502).send(oldal({
        cim: 'Átmeneti hiba', szin: '#d9534f',
        torzs: `<p>A szolgáltató nem válaszolt (${getu.status}). Kérjük, próbáld meg később.</p>`
      }));
      return;
    }

    const adat = await getu.json();
    const allapot = adat?.data?.status;

    if (allapot === 'active') {
      marMegerositve.set(email, true);
      res.status(200).send(oldal({
        cim: 'Már meg van erősítve ✅', szin: '#2e9e5b',
        torzs: '<p>A feliratkozásod már aktív — nincs több teendőd. Íme a kupond:</p>',
        kupon: 'UDVOZOL5'
      }));
      return;
    }

    // 2) unconfirmed -> active
    const put = await fetch(
      `${ML_BASE}/subscribers/${encodeURIComponent(email)}`,
      {
        method: 'PUT',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          Authorization: `Bearer ${kulcs}`
        },
        body: JSON.stringify({ status: 'active' })
      }
    );

    const putAdat = await put.json().catch(() => ({}));
    const ujAllapot = putAdat?.data?.status;

    if (put.ok && ujAllapot === 'active') {
      marMegerositve.set(email, true);
      // HOZZÁJÁRULÁS-NAPLÓZÁS (GDPR 7. cikk — bizonyíthatóság).
      // A feliratkozó MOST, aktív cselekedettel erősítette meg a hozzájárulást.
      // Ez a bizonyíték: ki, mikor, honnan. Nem blokkoló — ha nem megy, a
      // megerősítés akkor is érvényes (de logoljuk a hibát).
      try {
        await fetch(process.env.HOZZAJARULAS_WEBHOOK || 'https://kockaorszag.hu/api/hozzajarulas', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email,
            forras: 'reoptin-megerosites',
            urlap: '198607723660575914',
            idobelyeg: new Date().toISOString(),
            user_agent: (req.headers['user-agent'] || '').slice(0, 200)
          })
        });
      } catch (logHiba) {
        // a naplózás kudarca nem blokkolja a megerősítést
        console.error('hozzajarulas-naplo hiba:', logHiba?.message || logHiba);
      }
      res.status(200).send(oldal({
        cim: 'Sikeres megerősítés! ✅', szin: '#2e9e5b',
        torzs: `<p>Örülünk, hogy velünk maradsz — a feliratkozásod aktív, és a kedvezménykuponod érvényes.</p>`,
        kupon: 'UDVOZOL5'
      }));
      return;
    }

    res.status(502).send(oldal({
      cim: 'Nem sikerült', szin: '#d9534f',
      torzs: `<p>A megerősítés nem sikerült (${put.status}${ujAllapot ? ' / ' + ujAllapot : ''}). Kérjük, kattints újra a levélben lévő gombra.</p>`
    }));

  } catch (e) {
    res.status(500).send(oldal({
      cim: 'Átmeneti hiba', szin: '#d9534f',
      torzs: '<p>Váratlan hiba történt. Kérjük, próbáld meg később.</p>'
    }));
  }
}
