// Hírlevél betöltése + a linkek életővé tétele
const HONAP = {"01":"január","02":"február","03":"március","04":"április","05":"május","06":"június",
               "07":"július","08":"augusztus","09":"szeptember","10":"október","11":"november","12":"december"};
function datumSzoveg(iso){
  const [y,m,d]=(iso||"").split("-");
  return (y&&m&&d) ? (y+". "+(HONAP[m]||m)+" "+parseInt(d,10)+".") : (iso||"");
}
// Az azonosito kiolvasasa: eloszor a ?id= parametert, majd a regi /level/<id> format nezzuk
const ID = (function(){
  const q = new URLSearchParams(location.search).get("id");
  if (q) return q;
  return decodeURIComponent(location.pathname.replace(/^\/level\/?/, "").replace(/\/$/, ""));
})();

// A level HTML-jet "elő életővé" tesszük:
//  1) minden link target="_blank" + rel=noopener  -> a sandbox ne nyelje el
//  2) a halott [BONGESZO_URL] placeholder cseréje az oldal saját URL-jére
//  3) a szöveg/kepek betoltesi hibainak elrejtese
function eloLinkek(html){
  if(!html) return html;

  // 1) a halott placeholder
  const sajatUrl = location.href;
  html = html.replace(/\[BONGESZO_URL\]/g, sajatUrl);

  // 2) keressuk meg az osszes <a ...> nyito tagot es tegyuk ele a cel+rel-t
  html = html.replace(/<a\b([^>]*)>/gi, function(teljes, attrs){
    if(/\btarget\s*=/.test(attrs)) return teljes;
    if(/\bhref\s*=\s*["']\s*(#|javascript:|mailto:)/i.test(attrs)) return teljes;
    return '<a' + attrs + ' target="_blank" rel="noopener noreferrer">';
  });

  return html;
}

fetch("/data/archivum.json").then(r=>r.json()).then(d=>{
  const l = (d.levelek||[]).find(x => String(x.id) === ID);
  if(!l){ document.getElementById("cim").textContent = "A hírlevél nem található"; return; }
  document.title = (l.targy || l.cim || "Hírlevél") + " — Kockaország";
  document.getElementById("cim").textContent = l.targy || l.cim || "Hírlevél";
  document.getElementById("meta").textContent =
    "Kiküldve: " + datumSzoveg(l.datum) + (l.kikuldve ? "" : " (előkészítés alatt)");
  document.getElementById("allapot").innerHTML =
    '<span class="chip' + (l.kikuldve ? '' : ' draft') + '"><span class="pont"></span>' +
    (l.kikuldve?'Kiküldve':'Előkészítés') + '</span>';

  // Az iframe magassagat a benne levo level TELJES magassagahoz igazitjuk,
  // igy nem vagodik le a tartalom es nem lesz belso gorgetsav sem.
  const keret = document.getElementById("level");
  function magassagIgazit(){
    try{
      const d = keret.contentDocument || (keret.contentWindow && keret.contentWindow.document);
      if(!d) return;
      const h = Math.max(
        d.documentElement ? d.documentElement.scrollHeight : 0,
        d.body ? d.body.scrollHeight : 0,
        d.documentElement ? d.documentElement.offsetHeight : 0,
        d.body ? d.body.offsetHeight : 0
      );
      if(h > 100) keret.style.height = (h + 40) + "px";
    }catch(e){ /* sandbox: marad az alap magassag */ }
  }
  keret.addEventListener("load", function(){ setTimeout(magassagIgazit, 120); });
  // kep-betoltes utan ujramérünk (a kepek novelik a magassagot)
  setTimeout(magassagIgazit, 400); setTimeout(magassagIgazit, 1200); setTimeout(magassagIgazit, 2500);
  window.addEventListener("resize", magassagIgazit);

  keret.srcdoc = eloLinkek(l.html);
}).catch(()=>{ document.getElementById("cim").textContent = "Az archívum átmenetileg nem érhető el."; });
