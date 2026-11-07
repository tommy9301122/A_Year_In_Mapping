import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {hydrate, summarize} from '../server/analytics.mjs';
import {createHandler} from '../server/handler.mjs';
const snapshot = JSON.parse(await readFile(new URL('../data/snapshot.json', import.meta.url), 'utf8'));
const data = hydrate(snapshot);
test('all-mode report reconciles without double-counting favourites', () => {
  const r = summarize(data, new URLSearchParams({mode:'all',status:'all'}));
  assert.equal(r.overview.difficulties, data.details.length);
  assert.equal(r.overview.sets, new Set(data.sets.map(r=>r.beatmapset_id)).size);
  const favourites = new Map(data.sets.map(r=>[r.beatmapset_id,r.favourite_count]));
  assert.equal(r.overview.favourites, [...favourites.values()].reduce((a,b)=>a+b,0));
  assert.equal(r.overview.plays, data.details.reduce((a,b)=>a+b.playcount,0));
  assert.equal(r.genre.reduce((a,b)=>a+b.count,0),r.overview.sets);
  assert.equal(r.hosts.reduce((a,b)=>a+b.difficulties,0),data.details.filter(r=>!r.gd).length);
  assert.equal(r.hosts.reduce((a,b)=>a+b.plays,0)+r.guests.reduce((a,b)=>a+b.plays,0),r.overview.plays);
  assert.equal(r.guests.reduce((a,b)=>a+b.count,0),data.details.filter(r=>r.gd).length);
});
test('country and newcomer filters use hosts', () => {
  const r=summarize(data,new URLSearchParams({mode:'osu!',status:'Rank',country:'TW',new:'true'}));
  const selected=data.sets.filter(r=>r.mode==='osu!'&&r.status==='Rank'&&r.country==='TW'&&r.new_mapper===true);
  assert.equal(r.overview.sets,selected.length);
  assert.equal(r.overview.difficulties,selected.reduce((a,b)=>a+b.beatmap_count,0));
  assert.equal(r.overview.newcomers,r.overview.mappers);
});
test('empty results and invalid filters', () => {
  const r=summarize(data,new URLSearchParams({q:'__no_such_song_987654321__'}));
  assert.equal(r.overview.sets,0); assert.deepEqual(r.genre,[]);
  assert.throws(()=>summarize(data,new URLSearchParams({mode:'bad'})));
});
test('API rejects writes and private paths', async () => {
  const fetch=createHandler(snapshot,{'/':{body:'hello',type:'text/html'}});
  assert.equal((await fetch(new Request('https://test/api/report'))).status,200);
  assert.equal((await fetch(new Request('https://test/api/report?mode=bad'))).status,400);
  assert.equal((await fetch(new Request('https://test/.env'))).status,404);
  assert.equal((await fetch(new Request('https://test/',{method:'POST'}))).status,405);
  assert.equal(await (await fetch(new Request('https://test/',{method:'HEAD'}))).text(),'');
});
test('same title by different artists stays separate', () => {
  const sets=[{mode:'osu!',status:'Rank',beatmapset_id:1,title:'Same',artist:'A',mapper_id:1,playcount:0,beatmap_count:0,favourite_count:1},
    {mode:'osu!',status:'Rank',beatmapset_id:2,title:'Same',artist:'B',mapper_id:1,playcount:0,beatmap_count:0,favourite_count:1}];
  assert.equal(summarize({meta:{},sets,details:[]},new URLSearchParams()).songs.length,2);
});
