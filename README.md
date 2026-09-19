# Kockaország hírlevél-archívum

A `hirlevel.kockaorszag.hu` nyilvános oldala: hírlevél-archívum, feliratkozás,
double opt-in megerősítés és leiratkozás.

## Szerkezet

```
public/                          ← a deploy-gyökér (statikus, Vercel ezt szolgálja)
├── index.html                   → /              archívum (levél-lista, hónap-szűrő)
├── feliratkozas/index.html      → /feliratkozas  MailerLite űrlap (beágyazva)
├── hirlevel-megerosites/index.html → /hirlevel-megerosites  double opt-in megerősítés
├── leiratkozas/index.html       → /leiratkozas  leiratkozás
├── level/index.html             → /level/<id>    egy hírlevél megjelenítése
└── data/archivum.json           ← az archívum adatai
server.js                        ← CSAK lokális fejlesztéshez (a Vercel nem használja)
vercel.json                      ← Vercel-konfig (rewrite-ok, headerek)
```

## Lokális futtatás

```bash
node server.js          # http://127.0.0.1:8090
```

## Deploy

A Vercel a `public/` mappát szolgálja ki statikusan. A `vercel.json` tartalmazza
a rewrite-okat (`/level/:id`, `/hirlevel-megerosites`) és a biztonsági headereket.

## Fontos tudnivalók

- **A MailerLite embed azonosító `vmxiHa`** — NEM a hosszú builder-id (`45924038`).
- A `/hirlevel-megerosites` oldal a double opt-in **megerősítő link** célja
  (Ferenc 1B-döntése: `kockaorszag.hu/hirlevel-megerosites`).
- A kuponkód a confirm-oldalon: `UDVOZOL5` (5%, min. 10 000 Ft, 14 nap).
- **PII-szabály:** előfizetői adat NEM kerül a Vercel serverless függvényeibe —
  a feliratkozás közvetlenül a MailerLite-ba (EU) megy.
