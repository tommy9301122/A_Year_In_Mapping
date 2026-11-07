import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {createHandler} from '../server/handler.mjs';
const snapshot = JSON.parse(await readFile(new URL('../data/snapshot.json', import.meta.url), 'utf8'));
const server = createServer(async (req, res) => {
  try {
    const assets = {};
    for (const [path, file, type] of [['/', 'index.html', 'text/html'], ['/app.js', 'app.js', 'text/javascript'], ['/style.css', 'style.css', 'text/css']]) assets[path] = {body: await readFile(new URL(`../web/${file}`, import.meta.url), 'utf8'), type: `${type}; charset=utf-8`};
    const response = await createHandler(snapshot, assets)(new Request(`http://localhost${req.url}`, {method: req.method}));
    res.writeHead(response.status, Object.fromEntries(response.headers)); res.end(Buffer.from(await response.arrayBuffer()));
  } catch (e) {console.error(e); res.writeHead(500); res.end('Server error');}
});
server.listen(Number(process.env.PORT || 4173), '127.0.0.1', () => console.log('Local: http://127.0.0.1:4173'));
