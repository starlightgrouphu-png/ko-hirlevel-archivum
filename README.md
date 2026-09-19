# Kockaország hírlevél-archívum

A hirlevel.kockaorszag.hu statikus archívum-oldala.

## Szerkezet
- `public/index.html` — archívum főoldal (kártyák)
- `public/level/index.html` + `level.js` — egy levél megjelenítése (`/level/?id=<azonosító>`)
- `public/data/archivum.json` — a levelek adatai (HTML-lel)
- `public/ko-archivum.css`, `ko-kozos.css` — stíluslapok
- `vercel.json` — útvonal-beállítások

## Deploy
`bash /home/hermes/ko_hirlevel/scripts/ko_deploy.sh "uzenet"` — commit + push + Vercel deploy + ellenőrzés
