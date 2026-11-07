import {hydrate, summarize} from './analytics.mjs';
export function createHandler(snapshot, assets) {
  const data = hydrate(snapshot);
  return async function fetch(request) {
    const url = new URL(request.url);
    const headers = {'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'strict-origin-when-cross-origin',
      'Content-Security-Policy': "default-src 'self'; img-src 'self' https://assets.ppy.sh https://a.ppy.sh https://osu.ppy.sh; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'self' https://*.chatgpt.com https://chatgpt.com", 'Cache-Control': 'public, max-age=300'};
    if (!['GET', 'HEAD'].includes(request.method)) return new Response('Method not allowed', {status: 405, headers: {...headers, Allow: 'GET, HEAD'}});
    let body, type = 'application/json; charset=utf-8', status = 200;
    if (url.pathname === '/api/report') {
      try {body = JSON.stringify(summarize(data, url.searchParams));}
      catch {body = JSON.stringify({error: 'Invalid filters'}); status = 400;}
    } else if (url.pathname === '/api/health') {body = JSON.stringify({ok: true, release: data.meta.release, end: data.meta.end});}
    else if (assets[url.pathname]) {({body, type} = assets[url.pathname]);}
    else {body = 'Not found'; type = 'text/plain; charset=utf-8'; status = 404;}
    return new Response(request.method === 'HEAD' ? null : body, {status, headers: {...headers, 'Content-Type': type}});
  };
}
