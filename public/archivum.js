// A hírlevél-archívum főoldala: kártyák + keresés
const HONAP = {"01":"január","02":"február","03":"március","04":"április","05":"május","06":"június",
               "07":"július","08":"augusztus","09":"szeptember","10":"október","11":"november","12":"december"};

function datumSzoveg(iso){
  const [y,m,d] = (iso||"").split("-");
  return (y&&m&&d) ? (HONAP[m]||m).replace(/^./,c=>c.toUpperCase())+" "+parseInt(d,10)+". " : (iso||"");
}
function menekul(s){
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}
// nyers HTML -> olvasható szöveg
function tisztit(html){
  let t = String(html||"")
    .replace(/<style[\s\S]*?<\/style>/gi," ").replace(/<script[\s\S]*?<\/script>/gi," ")
    .replace(/<!--[\s\S]*?-->/g," ").replace(/<[^>]+>/g," ")
    .replace(/&nbsp;/g," ").replace(/&amp;/g,"&").replace(/&[a-z]+;/gi," ")
    .replace(/\s+/g," ").trim();
  return t.replace(/^Nem jelenik meg helyesen\??\s*/i,"").replace(/^Megnyitom böngészőben\s*/i,"");
}
function kivonat(html, max){
  const t = tisztit(html);
  return t.length > max ? t.slice(0, max).replace(/\s\S*$/,"") + "…" : t;
}
// olvasási idő (200 szó/perc, magyar átlag)
function olvasas(html){
  const szavak = tisztit(html).split(/\s+/).filter(Boolean).length;
  return Math.max(1, Math.round(szavak/200)) + " perc olvasás";
}
// képek száma
function kepSzam(html){
  const m = String(html||"").match(/<img\b/gi);
  return m ? m.length : 0;
}

fetch("/data/archivum.json").then(r=>r.json()).then(d=>{
  const levelek = (d.levelek||[]).slice();
  levelek.sort((a,b)=>String(b.datum||"").localeCompare(String(a.datum||"")));

  const racs  = document.getElementById("racs");
  const darab = document.getElementById("darab");
  const kereso = document.getElementById("kereso");
  const torles = document.getElementById("torles");
  const info   = document.getElementById("kereso-info");

  darab.textContent = levelek.length + " hírlevél";

  if(!levelek.length){
    racs.innerHTML = '<div class="uzenet"><div class="ikon">📭</div><p>Még nincs feltöltött hírlevél.</p></div>';
    return;
  }

  // ékezet nélküli összehasonlítás (hogy a "vizipisztoly" is találjon)
  const EKEZET = {"á":"a","é":"e","í":"i","ó":"o","ö":"o","ő":"o","ú":"u","ü":"u","ű":"u",
                  "Á":"a","É":"e","Í":"i","Ó":"o","Ö":"o","Ő":"o","Ú":"u","Ü":"u","Ű":"u"};
  function ekezet(s){
    return String(s||"").replace(/[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]/g, c => EKEZET[c] || c).toLowerCase();
  }

  // kereséshez előkészített szöveg
  levelek.forEach(l=>{
    l._cim   = l.cim || l.targy || "Hírlevél";
    l._targy = l.targy || "";
    l._keres = ekezet(l._targy + " " + l._cim + " " + tisztit(l.html||l.szoveg));
  });

  function rajzol(lista){
    if(!lista.length){
      racs.innerHTML = '<div class="uzenet"><div class="ikon">🔍</div>'
        + '<p>Nincs találat erre: „' + menekul(kereso.value) + '”</p></div>';
      return;
    }
    racs.innerHTML = lista.map(l=>{
      const kep = kepSzam(l.html||l.szoveg);
      const meta = '<span class="kartya-meta">'
        + '<span class="ido">' + olvasas(l.html||l.szoveg) + '</span>'
        + (kep ? '<span class="pontocske">·</span><span class="kepek">' + kep + ' kép</span>' : '')
        + '</span>';
      const kiv = kivonat(l.html||l.szoveg, 190);
      return '<a class="kartya" href="/level/?id='+encodeURIComponent(l.id)+'">'
        + '<span class="datum">' + menekul(datumSzoveg(l.datum)) + '</span>'
        + '<h3>' + menekul(l._targy || l._cim) + '</h3>'
        + (kiv ? '<p class="kivonat">' + menekul(kiv) + '</p>' : '')
        + '<span class="lablec">' + meta
        + '<span class="megnyit">Megnyitás <span class="nyil">→</span></span>'
        + '</span></a>';
    }).join("");
  }

  // szűrés
  function szur(){
    const q = ekezet((kereso.value||"").trim());
    torles.classList.toggle("latszik", !!q);
    if(!q){
      info.textContent = "";
      rajzol(levelek);
      return;
    }
    const szavak = q.split(/\s+/).filter(Boolean);
    const talalat = levelek.filter(l => szavak.every(sz => l._keres.includes(sz)));
    info.textContent = talalat.length + " találat a " + levelek.length + " hírlevélből";
    rajzol(talalat);
  }

  kereso.addEventListener("input", szur);
  torles.addEventListener("click", ()=>{ kereso.value=""; szur(); kereso.focus(); });
  // Esc üríti
  kereso.addEventListener("keydown", e=>{ if(e.key==="Escape"){ kereso.value=""; szur(); }});

  rajzol(levelek);
}).catch(()=>{
  document.getElementById("racs").innerHTML =
    '<div class="uzenet"><div class="ikon">⚠️</div><p>Az archívum átmenetileg nem érhető el.</p></div>';
});
