const $ = id => document.getElementById(id);
const fmt = n => Number(n).toLocaleString('en-US');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const palette = ['#80aaff','#80e5ff','#ff80ab','#ffcc80','#ffff80','#c6ff80','#b39ddb','#80cbc4','#ef9a9a','#c5cae9','#bcaaa4','#a5d6a7','#eeeeee'];
const profile = (id, name) => `<a class="person" href="https://osu.ppy.sh/users/${Number(id)}" target="_blank" rel="noopener"><img class="avatar" src="https://a.ppy.sh/${Number(id)}" alt="" loading="lazy"><span>${esc(name)}</span></a>`;
const flag = c => /^[A-Z]{2}$/.test(c) ? `<img class="flag" src="https://osu.ppy.sh/images/flags/${c}.png" alt="" loading="lazy" width="32" height="22">` : '<span class="flag" aria-hidden="true">—</span>';
const region = new Intl.DisplayNames(['en'], {type:'region'});
const countryName = c => c === 'Unknown' ? 'Unknown' : `${c} · ${region.of(c) || c}`;
let controller;
function table(id, headers, rows, render, limit=10) {
  let shown = limit;
  function draw() {
    $(id).innerHTML = rows.length ? `<div class="table-wrap"><table><thead><tr><th>#</th>${headers.map(h => `<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.slice(0,shown).map((r,i) => `<tr><td>${String(i+1).padStart(2,'0')}</td>${render(r)}</tr>`).join('')}</tbody></table></div>${rows.length>shown ? `<button class="more" type="button">Show more ↓ · ${shown} / ${fmt(rows.length)}</button>`:''}` : '<p class="empty">No data for these filters.</p>';
    $(id).querySelector('button')?.addEventListener('click', () => {shown += 20; draw();});
  } draw();
}
function chart(id, rows) {
  const total = rows.reduce((s,r) => s+r.count,0); let cursor=0;
  const stops = rows.map((r,i) => {const from=cursor; cursor+=r.count/(total||1)*100;return `${palette[i%palette.length]} ${from}% ${cursor}%`;});
  $(id).innerHTML = total ? `<div class="donut" role="img" aria-label="${esc(rows.map(r => `${r.name}: ${r.count}`).join(', '))}" style="background:conic-gradient(${stops.join(',')})"><div><b>${fmt(total)}</b><small>BEATMAPSETS</small></div></div><div class="legend">${rows.map((r,i) => `<div class="legend-row"><i style="background:${palette[i%palette.length]}"></i><span>${esc(r.name)}</span><b>${(r.count/total*100).toFixed(1)}%</b></div>`).join('')}</div>` : '<p class="empty">No data</p>';
}
const td = html => `<td>${html}</td>`;
function render(r) {
  const o=r.overview;
  $('release').textContent = r.meta.release === 'final' ? '2026 · Full-year snapshot' : '2026 · Preview — partial-year data';
  $('dates').textContent = `${r.meta.start} — ${r.meta.end} · UTC`;
  $('method-date').textContent = `Source: osu! API. Last source response: ${new Date(r.meta.fetchedAt).toISOString().replace('T',' ').slice(0,19)} UTC. ${r.meta.release === 'final' ? 'Full-year snapshot.' : 'Partial-year preview.'} No automatic updates.`;
  $('metrics').innerHTML = [[o.sets,'Beatmapsets'],[o.difficulties,'Beatmaps'],[o.mappers,'Mappers'],[o.newcomers,'New mappers'],[o.favourites,'Favourite count'],[o.plays,'Playcount']].map(([v,l]) => `<div class="metric"><p>${l}</p><strong>${fmt(v)}</strong></div>`).join('');
  chart('genre',r.genre);chart('language',r.language);
  table('mappers',['Mapper','Beatmapsets'],r.mappers,x=>td(profile(x.id,x.name))+td(`<span class="number">${fmt(x.count)}</span>`));
  table('countries',['Country','Beatmapsets','Mappers'],r.countries,x=>td(`<span class="country-cell">${flag(x.name)}<span>${esc(countryName(x.name))}</span></span>`)+td(fmt(x.count))+td(fmt(x.mappers)));
  for(const [id,rows,key,label] of [['favourite-table',r.favourites,'favourites','Favourites'],['play-table',r.plays,'plays','Playcount']]) table(id,['Beatmap','Mapper',label],rows,x=>td(`<a class="track" href="https://osu.ppy.sh/beatmapsets/${Number(x.id)}" target="_blank" rel="noopener"><img class="cover" src="https://assets.ppy.sh/beatmaps/${Number(x.id)}/covers/list@2x.jpg" alt="" loading="lazy"><span><b>${esc(x.title)}</b><small>${esc(x.artist)}</small></span></a>`)+td(`<a href="https://osu.ppy.sh/users/${Number(x.mapperId)}" target="_blank" rel="noopener">${esc(x.mapper)}</a>`)+td(`<span class="number">${fmt(x[key])}</span>`),6);
  table('songs',['Title / Artist','Beatmapsets'],r.songs,x=>td(`<span class="song">${esc(x.name)}<small>${esc(x.artist)}</small></span>`)+td(fmt(x.count)));
  table('artists',['Artist','Beatmapsets'],r.artists,x=>td(esc(x.name))+td(fmt(x.count)));
  table('guests',['Mapper','Beatmaps','Playcount'],r.guests,x=>td(profile(x.id,x.name))+td(fmt(x.count))+td(fmt(x.plays)),5);
  table('hosts',['Mapper','Beatmapsets','Beatmaps','Playcount'],r.hosts,x=>td(profile(x.id,x.name))+td(fmt(x.count))+td(fmt(x.difficulties))+td(fmt(x.plays)),5);
  const country=$('country'), value=country.value;
  country.innerHTML='<option value="">All countries</option>'+r.countriesAvailable.map(c=>`<option value="${esc(c)}">${esc(countryName(c))}</option>`).join('');country.value=value;
  $('notice').textContent=o.sets ? (o.unknownNewcomers ? `${o.unknownNewcomers} host(s) with unknown debut status excluded from new mapper counts.`:'') : 'No matching beatmapsets. Adjust the filters or select Reset.';
}
async function load() {
  controller?.abort(); controller=new AbortController(); const current=controller;
  const params=new URLSearchParams(new FormData($('filters'))); if($('filters').elements.new.checked) params.set('new','true');
  history.replaceState(null,'',`${location.pathname}?${params}`);
  $('report').setAttribute('aria-busy','true');$('notice').textContent='Loading…';
  try {const response=await fetch(`/api/report?${params}`,{signal:current.signal});if(!response.ok)throw new Error('Failed');render(await response.json());}
  catch(e){if(e.name!=='AbortError'){$('notice').innerHTML='Unable to load data. <button id="retry" type="button">Retry</button>';$('retry').onclick=load;}}
  finally{if(controller===current)$('report').setAttribute('aria-busy','false');}
}
const params=new URLSearchParams(location.search);
for(const name of ['mode','status','q'])if(params.has(name))$('filters').elements[name].value=params.get(name);
if(params.get('country')){$('country').add(new Option(params.get('country'),params.get('country')));$('country').value=params.get('country');}
$('filters').elements.new.checked=params.get('new')==='true';
let timer;$('filters').addEventListener('change',e=>{if(e.target.name!=='q')load();});
$('filters').elements.q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,300);});
$('filters').addEventListener('submit',e=>{e.preventDefault();clearTimeout(timer);load();});
$('filters').addEventListener('reset',()=>{clearTimeout(timer);setTimeout(load,0);});
const observer=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting)document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.hash===`#${e.target.id}`));},{rootMargin:'-10% 0px -65% 0px'});
document.querySelectorAll('#report>section').forEach(s=>observer.observe(s));
load();
