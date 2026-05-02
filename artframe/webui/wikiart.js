// WikiArt-Wrapper — alle Endpoints, die ohne Auth zuverlässig laufen.
//
// CORS-Workaround: Beim Auslieferung via http(s) gehen alle Calls über
// einen Netlify-Proxy (/wikiart/* → https://www.wikiart.org/*), damit
// die Same-Origin-Policy keine fetch()-Calls blockt. Beim Aufruf via
// file:// (offline-Test) wird direkt wikiart.org angesprochen.

const BASE = location.protocol === 'file:'
    ? 'https://www.wikiart.org'
    : '/wikiart';
const cache = new Map();

async function fetchJSON(url) {
    if (cache.has(url)) return cache.get(url);
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${r.status} ${url}`);
    const data = await r.json();
    cache.set(url, data);
    return data;
}

// ────── Gemälde eines Künstlers ────────────────────────────────────
export async function paintingsByArtist(slug, lang = 'en') {
    const url = `${BASE}/${lang}/App/Painting/PaintingsByArtist`
              + `?artistUrl=${encodeURIComponent(slug)}`;
    return await fetchJSON(url);
}

export async function paintingsBilingual(slug) {
    const [en, de] = await Promise.all([
        paintingsByArtist(slug, 'en').catch(() => []),
        paintingsByArtist(slug, 'de').catch(() => []),
    ]);
    const deMap = new Map((de || []).map(p => [p.contentId, p.title]));
    return (en || []).map(p => ({
        ...p,
        title_en: p.title || '',
        title_de: deMap.get(p.contentId) || '',
    }));
}

export async function mostViewedPaintings(page = 1, perPage = 50) {
    const url = `${BASE}/en/App/Painting/MostViewedPaintings`
              + `?json=2&inPage=${page}&itemsPerPage=${perPage}`;
    return await fetchJSON(url);
}

// ────── Kunstbewegungen ─────────────────────────────────────────────
// Liefert 14 Epochen-Kategorien + 189 Bewegungen, deutsche Titel wenn
// verfügbar. WICHTIG: Slugs sind ENGLISCH, denn der Such-Endpoint
// (`?json=3&searchterm=`) versteht nur englische Slugs.
export async function artMovementsTree() {
    const [en, de] = await Promise.all([
        fetchJSON(`${BASE}/en/App/Search/Artists-by-Art-Movement?json=2`),
        fetchJSON(`${BASE}/de/App/Search/Artists-by-Art-Movement?json=2`)
            .catch(() => null),
    ]);

    const deCatTitles = new Map();
    (de?.Categories || []).forEach(c => {
        const titles = c.Content?.Title?.Title || {};
        if (c._id?._oid) deCatTitles.set(c._id._oid, titles.de || '');
    });

    const categories = (en.Categories || []).map(c => {
        const id = c._id?._oid;
        const titles = c.Content?.Title?.Title || {};
        return {
            id,
            title:    titles.de || deCatTitles.get(id) || titles.en || '',
            title_en: titles.en || '',
            movements: [],
        };
    });
    const byId = new Map(categories.map(c => [c.id, c]));

    const enDwc = en.DictionariesWithCategories || {};
    const deDwc = de?.DictionariesWithCategories || {};

    for (const [catId, enMovs] of Object.entries(enDwc)) {
        const cat = byId.get(catId);
        if (!cat) continue;
        const deMovs = deDwc[catId] || [];
        enMovs.forEach((m, i) => {
            const slug = (m.Url || '').split('/').pop();
            const deTitle = deMovs[i]?.Title || '';
            cat.movements.push({
                slug,
                title: deTitle || m.Title || '',
                title_en: m.Title || '',
                count: +m.Count || 0,
            });
        });
        cat.movements.sort((a, b) => b.count - a.count);
    }

    return categories.filter(c => c.movements.length);
}

// ────── Genres (flach, 60 Stück) ───────────────────────────────────
export async function genresList() {
    const [en, de] = await Promise.all([
        fetchJSON(`${BASE}/en/App/Search/Artists-by-Genre?json=2`),
        fetchJSON(`${BASE}/de/App/Search/Artists-by-Genre?json=2`)
            .catch(() => null),
    ]);
    // EN/DE-Reihenfolge weicht ab → Match über Count + Position-Hash
    // ist riskant. Wir bauen eine Map: EN-Index → DE-Title nur wenn
    // der EN-Slug eindeutig zu einem DE-Eintrag mit gleichem Count
    // passt.
    const deBySlug = new Map();
    (de?.Dictionaries || []).forEach(d => {
        const slug = (d.Url || '').split('/').pop();
        deBySlug.set(slug, { title: d.Title, count: +d.Count });
    });

    const out = (en.Dictionaries || []).map(g => {
        const slug = (g.Url || '').split('/').pop();
        const enTitle = capitalize(g.Title || '');
        // Direkter Slug-Treffer in DE? (selten, da DE-Slugs übersetzt sind)
        const deDirect = deBySlug.get(slug);
        return {
            slug,
            title: deDirect?.title || enTitle,
            title_en: enTitle,
            count: +g.Count || 0,
        };
    });
    out.sort((a, b) => a.title.localeCompare(b.title, 'de'));
    return out;
}

// ────── Künstler einer Kunstbewegung / Genre ────────────────────────
export async function artistsByMovement(slug) {
    return await artistsByCategory('Artists-by-Art-Movement', slug);
}
export async function artistsByGenre(slug) {
    return await artistsByCategory('Artists-by-Genre', slug);
}
async function artistsByCategory(controller, slug) {
    const out = [];
    for (let page = 1; page < 50; page++) {
        const url = `${BASE}/en/App/Search/${controller}`
                  + `?json=3&searchterm=${encodeURIComponent(slug)}&page=${page}`;
        const j = await fetchJSON(url);
        const parsed = parseArtistsHtml(j.ArtistsHtml || '');
        out.push(...parsed);
        if (!j.CanLoadMoreArtists || parsed.length === 0) break;
    }
    return out;
}

// ────── Gemälde-Listen für Zufallsmodus ────────────────────────────
export async function paintingsByStyle(slug, maxPages = 10) {
    return await paintingsForCategory('paintings-by-style', slug, maxPages);
}
export async function paintingsByGenre(slug, maxPages = 10) {
    return await paintingsForCategory('paintings-by-genre', slug, maxPages);
}
export async function paintingsByTag(slug, maxPages = 10) {
    return await paintingsForCategory('tag', slug, maxPages);
}
async function paintingsForCategory(kind, slug, maxPages) {
    const out = [];
    for (let page = 1; page <= maxPages; page++) {
        const url = `${BASE}/en/${kind}/${encodeURIComponent(slug)}`
                  + `?json=2&page=${page}`;
        const j = await fetchJSON(url);
        const ps = j.Paintings || [];
        out.push(...ps);
        if (ps.length < 60) break;
    }
    return out.map(p => ({ ...p, title_en: p.title || '', title_de: '' }));
}

// ────── Vollständiger Künstler-Index (chronologisch sortiert) ───────
// 60 Seiten × 60 = ~3500 Künstler. Wird im Memory-Cache gehalten.
let _allArtistsPromise = null;
export function allArtists() {
    if (!_allArtistsPromise) _allArtistsPromise = loadAllArtists();
    return _allArtistsPromise;
}
async function loadAllArtists() {
    const out = [];
    for (let page = 1; page < 80; page++) {
        const url = `${BASE}/en/App/Search/chronological-artists`
                  + `?json=3&page=${page}`;
        const j = await fetchJSON(url);
        const parsed = parseArtistsHtml(j.ArtistsHtml || '');
        out.push(...parsed);
        if (!j.CanLoadMoreArtists || parsed.length === 0) break;
    }
    const seen = new Set();
    return out.filter(a => {
        if (seen.has(a.slug)) return false;
        seen.add(a.slug);
        return true;
    });
}

// ────── Helpers ─────────────────────────────────────────────────────
function parseArtistsHtml(html) {
    if (!html) return [];
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const out = [];
    // Nur die Top-Level-LI (kein .title / .text — das sind Innenliste).
    doc.querySelectorAll('li:not(.title):not(.text):not(.more)').forEach(li => {
        const a = li.querySelector('a[href^="/en/"]');
        if (!a) return;
        const slug = a.getAttribute('href').replace(/^\/en\//, '').split('/')[0];
        if (!slug) return;
        const name = a.getAttribute('title') || a.textContent.trim();
        const lifespan = li.querySelector('.text')?.textContent.trim() || '';
        const bg = a.getAttribute('style') || '';
        const m = bg.match(/url\(['"]?([^'")]+)['"]?\)/);
        out.push({ slug, name, lifespan, image: m ? m[1] : '' });
    });
    // Doppelte (durch verschachtelte LIs) wegfiltern.
    const seen = new Set();
    return out.filter(a => {
        if (seen.has(a.slug)) return false;
        seen.add(a.slug);
        return true;
    });
}

export function hdUrl(image) {
    return image ? image.replace('!Large.jpg', '!HD.jpg') : '';
}

// Wandelt eine WikiArt-CDN-URL (https://uploads3.wikiart.org/...) in
// einen same-origin Pfad (/wikiart-img/uploads3/...) um, damit fetch()
// CORS-frei darauf zugreifen kann (siehe netlify.toml-Redirect).
// Notwendig fuer das Herunterladen von Bildern fuer Favoriten-Offline.
// Bei file:// (lokaler Test) bleibt die Original-URL.
export function corsSafeImageUrl(url) {
    if (!url) return url;
    if (location.protocol === 'file:') return url;
    const m = url.match(/^https?:\/\/(uploads\d*)\.wikiart\.org\/(.+)$/);
    if (!m) return url;
    return `/wikiart-img/${m[1]}/${m[2]}`;
}

export function filterOrientation(paintings, orientation) {
    return paintings.filter(p => {
        const w = +p.width, h = +p.height;
        if (!w || !h) return false;
        return orientation === 'portrait' ? h > w : w > h;
    });
}

function capitalize(s) {
    return s.charAt(0).toUpperCase() + s.slice(1);
}
