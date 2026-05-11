// Express-Server für Nowify auf Coolify/Strato.
// Ersetzt:
//   - Netlify-Function /api/track (file-basiertes Now-Playing-Relay)
//   - Netlify-Redirect /wikiart/* → wikiart.org (CORS-Proxy für iframe)
//   - Netlify-Redirect /wikiart-img/:bucket/* → :bucket.wikiart.org (Bild-Proxy)
//   - Statisches Hosting der Vue-SPA aus ./public

import express from 'express';
import { promises as fs } from 'node:fs';
import path from 'node:path';

const PORT = Number(process.env.PORT) || 3000;
const DATA_DIR = process.env.DATA_DIR || './data';
const TRACK_RELAY_SECRET = process.env.TRACK_RELAY_SECRET || '';
const STALE_AFTER_MS = 2 * 60 * 1000;
const TRACK_FILE = path.join(DATA_DIR, 'now-playing.json');

await fs.mkdir(DATA_DIR, { recursive: true });

const app = express();
app.disable('x-powered-by');
app.set('trust proxy', true);
app.use(express.json({ limit: '64kb' }));

// ─── /api/track ────────────────────────────────────────────────────────────
// 1:1-Port der Netlify-Function. GET liefert aktuellen Track (oder idle wenn
// älter als 2 min). POST mit x-relay-secret schreibt einen neuen Track oder
// markiert idle.

async function readTrack() {
  try {
    const raw = await fs.readFile(TRACK_FILE, 'utf8');
    return JSON.parse(raw);
  } catch (err) {
    if (err.code === 'ENOENT') return null;
    throw err;
  }
}

async function writeTrack(record) {
  const tmp = TRACK_FILE + '.tmp';
  await fs.writeFile(tmp, JSON.stringify(record));
  await fs.rename(tmp, TRACK_FILE);
}

async function clearTrack() {
  try {
    await fs.unlink(TRACK_FILE);
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
  }
}

app.get('/api/track', async (_req, res) => {
  const data = await readTrack();
  if (!data) return res.json({ source: 'idle' });
  const age = Date.now() - (data.timestamp || 0);
  if (age > STALE_AFTER_MS) {
    return res.json({ source: 'idle', staleSince: data.timestamp });
  }
  res.json({ ...data, ageMs: age });
});

app.post('/api/track', async (req, res) => {
  if (!TRACK_RELAY_SECRET || req.get('x-relay-secret') !== TRACK_RELAY_SECRET) {
    return res.status(401).type('text/plain').send('Unauthorized');
  }
  const body = req.body;
  if (!body || typeof body !== 'object') {
    return res.status(400).type('text/plain').send('Invalid JSON');
  }
  if (body.source === 'idle') {
    await clearTrack();
    return res.json({ ok: true, cleared: true });
  }
  const record = {
    source: body.source || 'krp',
    title: body.title ?? null,
    artist: body.artist ?? null,
    album: body.album ?? null,
    cover: body.cover ?? null,
    station: body.station ?? null,
    stationId: body.stationId ?? null,
    timestamp: Date.now(),
  };
  await writeTrack(record);
  res.json({ ok: true, stored: record });
});

// ─── /wikiart/* + /wikiart-img/:bucket/* ──────────────────────────────────
// Reverse-Proxy für WikiArt — Frontend lädt dadurch ohne CORS-Probleme.

async function proxyWikiart(originUrl, req, res) {
  // Query-String mit weitergeben.
  const upstreamUrl = req.originalUrl.includes('?')
    ? `${originUrl}${req.originalUrl.slice(req.originalUrl.indexOf('?'))}`
    : originUrl;

  try {
    const upstream = await fetch(upstreamUrl, {
      method: req.method,
      headers: {
        'User-Agent': 'Nowify-Proxy/1.0',
        Accept: req.get('accept') || '*/*',
      },
      redirect: 'follow',
    });

    res.status(upstream.status);
    const ct = upstream.headers.get('content-type');
    if (ct) res.set('Content-Type', ct);
    const cc = upstream.headers.get('cache-control');
    if (cc) res.set('Cache-Control', cc);
    res.set('Access-Control-Allow-Origin', '*');

    if (upstream.body) {
      const reader = upstream.body.getReader();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        res.write(Buffer.from(value));
      }
    }
    res.end();
  } catch (err) {
    res.status(502).type('text/plain').send(`Upstream error: ${err.message}`);
  }
}

app.all('/wikiart/*', (req, res) => {
  const rest = req.params[0] || '';
  return proxyWikiart(`https://www.wikiart.org/${rest}`, req, res);
});

app.all('/wikiart-img/:bucket/*', (req, res) => {
  const bucket = req.params.bucket.replace(/[^a-z0-9-]/gi, ''); // nur safe chars
  const rest = req.params[0] || '';
  if (!bucket) return res.status(400).type('text/plain').send('bad bucket');
  return proxyWikiart(`https://${bucket}.wikiart.org/${rest}`, req, res);
});

// ─── Statische SPA + Fallback ─────────────────────────────────────────────

const PUBLIC_DIR = path.join(process.cwd(), 'public');
app.use(express.static(PUBLIC_DIR, {
  index: 'index.html',
  maxAge: '1h',
  setHeaders: (res, filePath) => {
    if (filePath.endsWith('.html')) res.set('Cache-Control', 'no-cache');
  },
}));

// Vue-SPA-Routing: alles was kein API/Proxy und keine Datei ist → index.html
app.get('*', (_req, res) => {
  res.sendFile(path.join(PUBLIC_DIR, 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Nowify-Server: listening on :${PORT}`);
  console.log(`  Data dir:           ${DATA_DIR}`);
  console.log(`  Track relay secret: ${TRACK_RELAY_SECRET ? 'set' : 'NOT SET — POST /api/track wird 401 zurückgeben'}`);
});
