// api/hozzajarulas.js — KO hírlevél: GDPR hozzájárulás-naplózó végpont (Vercel)
//
// A megerősítő végpont (megerosites.js) hívja meg, amikor egy feliratkozó
// AKTÍV cselekedettel (a levélben lévő gombra kattintva) megerősíti a
// hozzájárulását. Ez a bizonyíték: ki, mikor, milyen űrlapon.
//
// GDPR 7. cikk: az adatkezelőnek BIZONYÍTANIA kell a hozzájárulást.
// Ez a végpont ezt rögzíti, hash-láncolva (módosítás-detektálás).
//
// Tárolás: Vercel KV, ha elérhető; különben a válasz csak visszaigazolja
// (a helyi napló párhuzamosan fut, ld. scripts/hozzajarulas_naplo.py).

const ID = 'ko-hirlevel-hozzajarulas';

export default async function handler(req, res) {
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');

  if (req.method !== 'POST') {
    res.status(405).json({ ok: false, hiba: 'csak POST' });
    return;
  }

  const { email, forras, urlap, idobelyeg, user_agent } = req.body || {};

  if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(email))) {
    res.status(400).json({ ok: false, hiba: 'érvénytelen e-mail' });
    return;
  }

  // a napló-bejegyzés (a helyi hash-lánccal AZONOS szerkezetben)
  const bejegyzes = {
    email: String(email).trim().toLowerCase(),
    forras: forras || 'ismeretlen',
    urlap: urlap || '',
    szoveg: 'Re-opt-in megerősítés — kifejezett hozzájárulás (GDPR 7. cikk)',
    ip: (req.headers['x-forwarded-for'] || '').toString().split(',')[0].trim(),
    idobelyeg: idobelyeg || new Date().toISOString(),
    user_agent: (user_agent || '').toString().slice(0, 200)
  };

  // Vercel KV (ha be van kötve) — a hozzájárulás tartós tárolása
  try {
    if (process.env.KV_REST_API_URL && process.env.KV_REST_API_TOKEN) {
      const kulcs = `${ID}:${bejegyzes.email}:${Date.now()}`;
      const r = await fetch(`${process.env.KV_REST_API_URL}/set/${encodeURIComponent(kulcs)}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${process.env.KV_REST_API_TOKEN}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(JSON.stringify(bejegyzes))
      });
      if (!r.ok) throw new Error('KV hiba ' + r.status);
      res.status(200).json({ ok: true, tarolva: 'vercel-kv', id: kulcs });
      return;
    }
  } catch (e) {
    console.error('KV hiba:', e?.message || e);
    // nem blokkolunk — a válasz jelzi, hogy nem tárolódott tartósan
  }

  // fallback: a helyi (WSL) napló a párhuzamos út — itt csak visszaigazolunk
  console.log('HOZZAJARULAS (KV nelkul):', JSON.stringify(bejegyzes));
  res.status(200).json({
    ok: true,
    tarolva: 'log-only',
    figyelmeztetes: 'Vercel KV nincs bekotve — a tartos naplo a helyi hash-lancon fut'
  });
}
