const $ = id => document.getElementById(id);
const fmt = n => Number(n).toLocaleString('en-US');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const palette = ['#ff8c77','#b5d7c5','#8aacf1','#c9a1df','#ebca82','#83c9c6','#c77c98','#9ea2a4','#719376','#b29a87','#838bbb','#bdad70','#78a4b5'];
const profile = (id, name) => `<a class="person" href="https://osu.ppy.sh/users/${Number(id)}" target="_blank" rel="noopener"><img class="avatar" src="https://a.ppy.sh/${Number(id)}" alt="" loading="lazy"><span>${esc(name)}</span></a>`;
const flag = c => /^[A-Z]{2}$/.test(c) ? String.fromCodePoint(...[...c].map(x => x.charCodeAt(0) + 127397)) : '—';
const region = new Intl.DisplayNames(['zh-Hant'], {type:'region'});
const countryName = c => c === 'Unknown' ? '未知' : `${c} · ${region.of(c) || c}`;
let controller;
function table(id, headers, rows, render, limit=10) {
  let shown = limit;
  function draw() {
    $(id).innerHTML = rows.length ? `<div class="table-wrap"><table><thead><tr><th>#</th>${headers.map(h => `<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.slice(0,shown).map((r,i) => `<tr><td>${String(i+1).padStart(2,'0')}</td>${render(r)}</tr>`).join('')}</tbody></table></div>${rows.length>shown ? `<button class="more" type="button">顯示更多 ↓ · ${shown} / ${fmt(rows.length)}</button>`:''}` : '<p class="empty">此篩選條件沒有資料。</p>';
    $(id).querySelector('button')?.addEventListener('click', () => {shown += 20; draw();});
  } draw();
}
function chart(id, rows) {
  const total = rows.reduce((s,r) => s+r.count,0); let cursor=0;
  const stops = rows.map((r,i) => {const from=cursor; cursor+=r.count/(total||1)*100;return `${palette[i%palette.length]} ${from}% ${cursor}%`;});
  $(id).innerHTML = total ? `<div class="donut" role="img" aria-label="${esc(rows.map(r => `${r.name}: ${r.count}`).join(', '))}" style="background:conic-gradient(${stops.join(',')})"><div><b>${fmt(total)}</b><small>BEATMAPSETS</small></div></div><div class="legend">${rows.map((r,i) => `<div class="legend-row"><i style="background:${palette[i%palette.length]}"></i><span>${esc(r.name)}</span><b>${(r.count/total*100).toFixed(1)}%</b></div>`).join('')}</div>` : '<p class="empty">沒有資料</p>';
}
const td = html => `<td>${html}</td>`;
function render(r) {
  const o=r.overview;
  $('release').textContent = r.meta.release === 'final' ? '● 2026 年度正式版' : '● 2026 預覽快照 · 尚非全年最終數據';
  $('dates').textContent = `${r.meta.start} — ${r.meta.end} · UTC`;
  $('method-date').textContent = `資料來自 osu! API，最後來源回應：${new Date(r.meta.fetchedAt).toISOString().replace('T',' ').slice(0,19)} UTC。此版本為${r.meta.release === 'final' ? '全年正式快照' : '年度結束前的預覽快照'}，不會自動更新。`;
  $('metrics').innerHTML = [[o.sets,'圖集','BEATMAPSETS'],[o.difficulties,'難度','DIFFICULTIES'],[o.mappers,'主創','MAPPERS'],[o.newcomers,'新主創','NEW MAPPERS'],[o.favourites,'收藏次數','FAVOURITES'],[o.plays,'遊玩次數','PLAYCOUNT']].map(([v,l,en]) => `<div class="metric"><p>${l}</p><strong>${fmt(v)}</strong><small>${en}</small></div>`).join('');
  chart('genre',r.genre);chart('language',r.language);
  table('mappers',['Mapper','圖集'],r.mappers,x=>td(profile(x.id,x.name))+td(`<span class="number">${fmt(x.count)}</span>`));
  table('countries',['國家','圖集','主創'],r.countries,x=>td(`<span class="flag">${flag(x.name)}</span>${esc(countryName(x.name))}`)+td(fmt(x.count))+td(fmt(x.mappers)));
  for(const [id,rows,key,label] of [['favourite-table',r.favourites,'favourites','收藏'],['play-table',r.plays,'plays','遊玩次數']]) table(id,['Beatmap','Mapper',label],rows,x=>td(`<a class="track" href="https://osu.ppy.sh/beatmapsets/${Number(x.id)}" target="_blank" rel="noopener"><img class="cover" src="https://assets.ppy.sh/beatmaps/${Number(x.id)}/covers/list@2x.jpg" alt="" loading="lazy"><span><b>${esc(x.title)}</b><small>${esc(x.artist)}</small></span></a>`)+td(`<a href="https://osu.ppy.sh/users/${Number(x.mapperId)}" target="_blank" rel="noopener">${esc(x.mapper)}</a>`)+td(`<span class="number">${fmt(x[key])}</span>`),6);
  table('songs',['歌曲 / 藝人','圖集'],r.songs,x=>td(`<span class="song">${esc(x.name)}<small>${esc(x.artist)}</small></span>`)+td(fmt(x.count)));
  table('artists',['藝人','圖集'],r.artists,x=>td(esc(x.name))+td(fmt(x.count)));
  table('guests',['Mapper','GD 難度','遊玩次數'],r.guests,x=>td(profile(x.id,x.name))+td(fmt(x.count))+td(fmt(x.plays)),5);
  table('hosts',['Mapper','圖集','難度','遊玩次數'],r.hosts,x=>td(profile(x.id,x.name))+td(fmt(x.count))+td(fmt(x.difficulties))+td(fmt(x.plays)),5);
  const country=$('country'), value=country.value;
  country.innerHTML='<option value="">所有國家</option>'+r.countriesAvailable.map(c=>`<option value="${esc(c)}">${esc(countryName(c))}</option>`).join('');country.value=value;
  $('notice').textContent=o.sets ? (o.unknownNewcomers ? `${o.unknownNewcomers} 位主創的新人身分未知，未列入新主創人數。`:'') : '沒有符合條件的圖集。請調整篩選或按「重設」。';
}
async function load() {
  controller?.abort(); controller=new AbortController(); const current=controller;
  const params=new URLSearchParams(new FormData($('filters'))); if($('filters').elements.new.checked) params.set('new','true');
  history.replaceState(null,'',`${location.pathname}?${params}`);
  $('report').setAttribute('aria-busy','true');$('notice').textContent='正在整理這段創作回憶…';
  try {const response=await fetch(`/api/report?${params}`,{signal:current.signal});if(!response.ok)throw new Error('Failed');render(await response.json());}
  catch(e){if(e.name!=='AbortError'){$('notice').innerHTML='資料載入失敗。<button id="retry" type="button">重新載入</button>';$('retry').onclick=load;}}
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
