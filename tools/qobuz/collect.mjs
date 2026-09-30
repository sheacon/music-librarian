// Metadata collector using the maintained @kud/qobuz-cli client dependency.
import {createTransport} from '@kud/qobuz';
import {readFile, writeFile, rename, mkdir} from 'node:fs/promises';
import {homedir} from 'node:os';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as sleep} from 'node:timers/promises';

export async function pages(get, endpoint, key, params) {
    const result = [], seen = new Set(), pageSignatures = new Set();
    let offset = 0;
    for (;;) {
      const data = await get(endpoint, {...params, limit:100, offset});
      const block = data[key];
      if (!block || !Array.isArray(block.items) || !Number.isInteger(block.total)) throw new Error(`Unexpected ${endpoint} pagination`);
      if (!block.items.length && offset < block.total) throw new Error(`Incomplete ${endpoint} pagination`);
      const signature = block.items.map(item => String(item.id)).join(',');
      if (block.items.length && pageSignatures.has(signature)) throw new Error(`Repeated ${endpoint} page`);
      pageSignatures.add(signature);
      for (const item of block.items) {
        if (!item.id) throw new Error(`Invalid ${endpoint} item`);
        if (!seen.has(String(item.id))) { seen.add(String(item.id)); result.push(item); }
      }
      offset += block.items.length;
      if (offset >= block.total) return result;
    }
  }

export function workKey(album) {
  const title = album.title.replace(/\s*[\[(][^\])]*(?:deluxe|remaster|expanded|anniversary|edition)[^\])]*[\])]/gi, '').replace(/\s+/g, ' ').trim().toLowerCase();
  return String(album.artist?.id ?? '') + '|' + title;
}

export async function classifyCandidates(get, albums, since, through) {
  const keys = new Set(albums.filter(a => a.release_date_original >= since && a.release_date_original <= through).map(workKey));
  const pending = albums.filter(a => keys.has(workKey(a)));
  async function worker() {
    while (pending.length) {
      const album = pending.shift();
      const details = await get('album/get', {album_id:album.id});
      if (String(details.id) !== String(album.id)) throw new Error('Release metadata ID mismatch');
      Object.assign(album, details);
    }
  }
  await Promise.all([worker(), worker(), worker()]);
}

async function main() {
  const outputIndex = process.argv.indexOf('--output');
  if (outputIndex < 0 || !process.argv[outputIndex + 1]) throw new Error('Use --output <snapshot.json>');
  const output = process.argv[outputIndex + 1];
  const since = process.argv[process.argv.indexOf('--since') + 1];
  const through = process.argv[process.argv.indexOf('--through') + 1];
  if (!/^\d{4}-\d{2}-\d{2}$/.test(since ?? '') || !/^\d{4}-\d{2}-\d{2}$/.test(through ?? '')) throw new Error('Provide --since and --through dates');
  const auth = JSON.parse(await readFile(`${homedir()}/.config/music-librarian/qobuz-auth.json`, 'utf8'));
  const client = createTransport({appId: auth.app_id, token: auth.token,
    fetchImpl: (url, options) => fetch(url, {...options, signal: AbortSignal.timeout(45000)})});
  async function get(endpoint, params) {
    for (let attempt = 0; attempt < 4; attempt++) {
      try { return await client.get(endpoint, params); }
      catch (error) {
        if ([401, 403].includes(error.status)) throw new Error('Qobuz sign-in expired; run python -m music_librarian.qobuz_auth');
        if (attempt === 3 || (error.status && ![429, 500, 502, 503, 504].includes(error.status))) {
          throw new Error(`Qobuz ${endpoint} failed${error.status ? ` (HTTP ${error.status})` : ''}`);
        }
        await sleep(1000 * 2 ** attempt);
      }
    }
  }
  const artists = new Map(), counts = {};
  const add = artist => { if (artist?.id && artist?.name) artists.set(String(artist.id), artist.name); };
  for (const type of ['albums', 'tracks', 'artists']) {
    const items = await pages(get, 'favorite/getUserFavorites', type, {type});
    counts[`favorite_${type}`] = items.length;
    for (const item of items) {
      if (type === 'artists') add(item);
      else if (type === 'tracks') { add(item.performer); add(item.album?.artist); }
      else add(item.artist);
      for (const artist of item.artists ?? item.album?.artists ?? []) add(artist);
    }
  }
  for (const type of ['albums', 'tracks']) {
    const items = await pages(get, 'purchase/getUserPurchases', type, {type});
    counts[`purchased_${type}`] = items.length;
    for (const item of items) {
      add(type === 'albums' ? item.artist : item.performer);
      if (type === 'tracks') add(item.album?.artist);
      for (const artist of item.artists ?? item.album?.artists ?? []) add(artist);
    }
  }
  if (!artists.size) throw new Error('No library artists returned');
  console.log(`Loaded ${artists.size} artists; ${JSON.stringify(counts)}`);
  const albums = new Map();
  let completed = 0;
  const remaining = [...artists.keys()];
  async function worker() {
    while (remaining.length) {
      const id = remaining.shift();
      const items = await pages(get, 'artist/get', 'albums', {artist_id:id, extra:'albums'});
      for (const album of items) {
        if (String(album.artist?.id) === id || album.artists?.some(a => String(a.id) === id)) albums.set(String(album.id), album);
      }
      if (++completed % 25 === 0) console.log(`Checked ${completed}/${artists.size} artists`);
      await sleep(200);
    }
  }
  await Promise.all([worker(), worker(), worker()]);
  await classifyCandidates(get, [...albums.values()], since, through);
  await mkdir(dirname(output), {recursive:true});
  const temp = `${output}.${process.pid}.tmp`;
  await writeFile(temp, JSON.stringify({collected_at:new Date().toISOString(), counts, artists:Object.fromEntries(artists), albums:[...albums.values()]}), {mode:0o600});
  await rename(temp, output);
  console.log(`Collected ${albums.size} releases across ${artists.size} artists.`);
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => {console.error(error.message); process.exit(1);});
}
