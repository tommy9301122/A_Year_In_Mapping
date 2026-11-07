export function hydrate(snapshot) {
  const rows = (columns, values) => values.map(row => Object.fromEntries(columns.map((c, i) => [c, row[i]])));
  return {meta: snapshot.meta, sets: rows(snapshot.setColumns, snapshot.sets), details: rows(snapshot.detailColumns, snapshot.details)};
}
const sum = (rows, field) => rows.reduce((n, r) => n + (Number(r[field]) || 0), 0);
const unique = (rows, field) => new Set(rows.map(r => r[field])).size;
function group(rows, key) {
  const result = new Map();
  for (const row of rows) { const k = key(row); if (!result.has(k)) result.set(k, []); result.get(k).push(row); }
  return [...result.entries()];
}
const sorted = (rows, field) => rows.sort((a, b) => b[field] - a[field] || String(a.name ?? a.id).localeCompare(String(b.name ?? b.id)));
const distribution = (sets, field) => sorted(group(sets, r => r[field] || 'Unknown').map(([name, rows]) => ({name, count: unique(rows, 'beatmapset_id')})), 'count');
export function summarize(data, params) {
  const mode = params.get('mode') ?? 'osu!';
  const status = params.get('status') ?? 'Rank';
  const country = params.get('country') ?? '';
  const fresh = params.get('new') === 'true';
  const query = (params.get('q') ?? '').trim().toLocaleLowerCase().slice(0, 120);
  if (!['all', 'osu!', 'osu!taiko', 'osu!catch', 'osu!mania'].includes(mode) || !['all', 'Rank', 'Love'].includes(status)) throw new Error('Invalid filter');
  // Country and newcomer filters always describe the host, including GD tables.
  const selected = data.sets.filter(r => (mode === 'all' || r.mode === mode) && (status === 'all' || r.status === status)
    && (!country || (r.country || 'Unknown') === country) && (!fresh || r.new_mapper === true)
    && (!query || [r.title, r.artist, r.mapper].some(v => String(v ?? '').toLocaleLowerCase().includes(query))));
  const selectedKeys = new Set(selected.map(r => `${r.beatmapset_id}:${r.mode}`));
  const details = data.details.filter(r => selectedKeys.has(`${r.beatmapset_id}:${r.mode}`));
  // Collapse set×mode before summing favourites or counting songs.
  const sets = group(selected, r => r.beatmapset_id).map(([id, rows]) => ({...rows[0], id,
    playcount: sum(rows, 'playcount'), beatmap_count: sum(rows, 'beatmap_count'), favourite_count: Math.max(...rows.map(r => r.favourite_count))}));
  const mappers = sorted(group(sets, r => r.mapper_id).map(([id, rows]) => ({id, name: rows[0].mapper || `User ${id}`, country: rows[0].country,
    count: rows.length, difficulties: sum(rows, 'beatmap_count'), plays: sum(rows, 'playcount')})), 'count');
  const countries = sorted(group(sets, r => r.country || 'Unknown').map(([name, rows]) => ({name, count: rows.length, mappers: unique(rows, 'mapper_id')})), 'count');
  const guests = sorted(group(details.filter(r => Boolean(r.gd)), r => r.gder_id).map(([id, rows]) => ({id, name: rows[0].mapper || `User ${id}`, count: rows.length, plays: sum(rows, 'playcount')})), 'count');
  const hosts = sorted(group(details.filter(r => !r.gd), r => r.gder_id).map(([id, rows]) => ({id, name: rows[0].mapper || `User ${id}`, count: unique(rows, 'beatmapset_id'),
    difficulties: rows.length, plays: sum(rows, 'playcount')})), 'plays');
  return {meta: data.meta, filters: {mode, status, country, new: fresh, q: query},
    countriesAvailable: [...new Set(data.sets.map(r => r.country || 'Unknown'))].sort(),
    overview: {sets: sets.length, difficulties: details.length, mappers: mappers.length,
      newcomers: unique(sets.filter(r => r.new_mapper === true), 'mapper_id'), unknownNewcomers: unique(sets.filter(r => r.new_mapper == null), 'mapper_id'),
      favourites: sum(sets, 'favourite_count'), plays: sum(details, 'playcount')},
    genre: distribution(sets, 'genre'), language: distribution(sets, 'language'), mappers, countries, guests, hosts,
    favourites: sorted([...sets], 'favourite_count').map(card), plays: sorted([...sets], 'playcount').map(card),
    songs: sorted(group(sets, r => JSON.stringify([r.title, r.artist])).map(([, rows]) => ({name: rows[0].title, artist: rows[0].artist, count: rows.length})), 'count'),
    artists: distribution(sets, 'artist')};
}
function card(r) {return {id: r.id, title: r.title, artist: r.artist, mapper: r.mapper || `User ${r.mapper_id}`, mapperId: r.mapper_id, favourites: r.favourite_count, plays: r.playcount};}
