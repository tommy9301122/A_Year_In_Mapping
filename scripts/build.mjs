import {readFile, mkdir, writeFile, copyFile} from 'node:fs/promises';
const snapshot = JSON.parse(await readFile('data/snapshot.json', 'utf8'));
const assets = {};
for (const [path, file, type] of [['/', 'index.html', 'text/html'], ['/app.js', 'app.js', 'text/javascript'], ['/style.css', 'style.css', 'text/css']]) {
  assets[path] = {body: await readFile(`web/${file}`, 'utf8'), type: `${type}; charset=utf-8`};
}
let analytics = await readFile('server/analytics.mjs', 'utf8');
let handler = (await readFile('server/handler.mjs', 'utf8')).replace("import {hydrate, summarize} from './analytics.mjs';", '');
await mkdir('dist/server', {recursive: true});
await mkdir('dist/.openai', {recursive: true});
await writeFile('dist/server/index.js', `${analytics}\n${handler}\nexport default {fetch: createHandler(${JSON.stringify(snapshot)}, ${JSON.stringify(assets)})};\n`);
await copyFile('.openai/hosting.json', 'dist/.openai/hosting.json');
console.log(`Built Worker with ${snapshot.details.length} difficulties (${snapshot.meta.release}).`);
