// Artframe — TV-freundlicher Browser für WikiArt.
// Steuerung: ↑↓←→ Enter Esc/Backspace · funktioniert mit FLIRC-Remote
// und normaler Tastatur identisch.

import {
    paintingsBilingual,
    mostViewedPaintings,
    hdUrl,
    filterOrientation,
    artMovementsTree,
    artistsByMovement,
    genresList,
    artistsByGenre,
    paintingsByStyle,
    paintingsByGenre,
    paintingsByTag,
    allArtists,
} from './wikiart.js';

// ────── Top-level menu ──────────────────────────────────────────────
const MAIN_MENU = [
    { label: 'Künstler A–Z',    go: () => showAlphabet() },
    { label: 'Kunstbewegungen', go: () => showMovementCategories() },
    { label: 'Genres',          go: () => showGenres() },
    { label: 'Stile',           go: () => showStyleCategories() },
    { label: 'Themen',          go: () => showTags() },
    { label: 'Beliebt',         go: () => slideshowPopular() },
    { label: 'Favoriten',       go: () => slideshowFavorites() },
    { label: 'Zufall',          go: () => slideshowRandomArtist() },
    { label: 'Einstellungen',   go: () => showSettings() },
];

const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('');

// ────── Kuratierte Themen-Tags (alle ≥50 Werke geprüft) ────────────
const TAGS = [
    { label: 'Mythologie',     slug: 'mythology' },
    { label: 'Blumen',         slug: 'flower' },
    { label: 'Berge',          slug: 'mountain' },
    { label: 'Meer',           slug: 'sea' },
    { label: 'Wald',           slug: 'forest' },
    { label: 'Winter',         slug: 'winter' },
    { label: 'Pferde',         slug: 'horse' },
    { label: 'Fluss',          slug: 'river' },
    { label: 'Vögel',          slug: 'birds' },
    { label: 'Licht',          slug: 'light' },
    { label: 'Kinder',         slug: 'children' },
    { label: 'Frühling',       slug: 'spring' },
    { label: 'Herbst',         slug: 'autumn' },
    { label: 'Nacht',          slug: 'night' },
    { label: 'Hunde',          slug: 'dogs' },
    { label: 'Straße',         slug: 'street' },
    { label: 'Sommer',         slug: 'summer' },
    { label: 'Schiff',         slug: 'ship' },
    { label: 'Fische',         slug: 'fish' },
    { label: 'Lesen',          slug: 'reading' },
    { label: 'Katzen',         slug: 'cats' },
    { label: 'Tod',            slug: 'death' },
    { label: 'Sonnenaufgang',  slug: 'sunrise' },
    { label: 'Garten',         slug: 'garden' },
];

// ────── Persistente Einstellungen ──────────────────────────────────
const STORAGE_KEY = 'artframe.v1';
const DEFAULTS = {
    orient: null,
    autoBoot: false,
    sleepEnabled: true,
    sleepFrom: '23:00',
    sleepTo:   '07:00',
    lastNav:   null,
    // Diashow
    slideDurationSec: 12,    // wie lange jedes Bild stehen bleibt
    osdHideAfterSec: 8,      // wie lange das OSD nach Bildwechsel sichtbar ist (0 = immer)
    imageFit: 'contain',     // 'contain' = ganzes Bild sichtbar (mit Raendern) / 'cover' = Bildschirm fuellen (croppt)
    // Passepartout (Rahmen-Farbe statt schwarz)
    mattingEnabled: false,
    mattingColor: '#0a0a0a',
};

// Auswahl-Optionen fuer das Einstellungs-Menue
const SLIDE_DURATIONS  = [5, 10, 15, 20, 30, 60, 120, 300];
const OSD_DURATIONS    = [0, 3, 5, 8, 15, 30];   // 0 = immer sichtbar
const IMAGE_FITS       = ['contain', 'cover'];
const MATTING_COLORS = [
    { hex: '#0a0a0a', label: 'Schwarz'      },
    { hex: '#2a2a2a', label: 'Anthrazit'    },
    { hex: '#4a4a4a', label: 'Tiefgrau'     },
    { hex: '#7d7468', label: 'Sandstein'    },
    { hex: '#c4b899', label: 'Pergament'    },
    { hex: '#e8e4dc', label: 'Off-White'    },
    { hex: '#f5f1ea', label: 'Creme'        },
    { hex: '#1a2238', label: 'Dunkelblau'   },
    { hex: '#1f3329', label: 'Tannengrün'   },
    { hex: '#3d1a1a', label: 'Bordeaux'     },
];
const TIMES = ['20:00','21:00','22:00','23:00','00:00','01:00','06:00','07:00','08:00','09:00'];
function loadSettings() {
    try {
        const s = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        return { ...DEFAULTS, ...s };
    } catch { return { ...DEFAULTS }; }
}
function saveSettings(patch) {
    const cur = loadSettings();
    const next = { ...cur, ...patch };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    return next;
}

// ────── State ───────────────────────────────────────────────────────
const state = {
    view:        'orient',
    orientation: null,
    cursor:      0,
    breadcrumb:  [],
    list:        null,
    listStack:   [],   // Stack vergangener Listen für Zurück-Navigation.
    slideshow:   null,
};

const $app = document.getElementById('app');

// Boot: Auto-Boot-Modus überspringt das Format-Picker und startet
// direkt die zuletzt gewählte Diashow.
boot();
function boot() {
    const s = loadSettings();
    if (s.autoBoot && s.orient && s.lastNav) {
        state.orientation = s.orient;
        resumeLastNav(s.lastNav).catch(() => showOrient());
    } else {
        showOrient();
    }
    startSleepWatcher();
}

async function resumeLastNav(nav) {
    switch (nav.kind) {
        case 'artist':    return slideshowFromArtist({ slug: nav.slug, name: nav.label });
        case 'style':     return slideshowFromCategory('style', nav.slug, nav.label);
        case 'genre':     return slideshowFromCategory('genre', nav.slug, nav.label);
        case 'tag':       return slideshowFromTag({ slug: nav.slug, label: nav.label });
        case 'popular':   return slideshowPopular();
        case 'favorites': return slideshowFavorites();
        case 'random':    return slideshowRandomArtist();
        default:          showOrient();
    }
}

// ────── Boot — Orientation picker ──────────────────────────────────
function showOrient() {
    state.view = 'orient';
    state.cursor = 0;
    $app.innerHTML = `
        <div class="orient">
            <h1>Artframe</h1>
            <div class="hint">Format wählen — ← → und Enter</div>
            <div class="tiles">
                <div class="tile" data-orient="landscape">
                    <div class="tile-frame landscape"></div>
                    <div class="tile-label">Querformat</div>
                </div>
                <div class="tile" data-orient="portrait">
                    <div class="tile-frame portrait"></div>
                    <div class="tile-label">Hochformat</div>
                </div>
            </div>
        </div>`;
    paintTiles();
}
function paintTiles() {
    document.querySelectorAll('.orient .tile').forEach((el, i) => {
        el.classList.toggle('selected', i === state.cursor);
    });
}

// ────── Main menu ───────────────────────────────────────────────────
function showMenu() {
    state.view = 'menu';
    state.cursor = 0;
    state.breadcrumb = [];
    state.listStack = [];
    state.list = { items: MAIN_MENU };
    allArtists().catch(() => {});  // Index im Hintergrund vorladen.
    artMovementsTree().catch(() => {});
    renderMenu();
}
function renderMenu() {
    $app.innerHTML = `
        <div class="menu">
            <h2>Artframe</h2>
            ${state.list.items.map((it,i) => `
                <div class="menu-item ${i === state.cursor ? 'selected' : ''}">
                    ${escape(it.label)}
                </div>`).join('')}
        </div>`;
}
function paintMenu() {
    document.querySelectorAll('.menu .menu-item').forEach((el, i) =>
        el.classList.toggle('selected', i === state.cursor));
}

// ────── Künstler A–Z ────────────────────────────────────────────────
function showAlphabet() {
    pushBC('menu');
    state.view = 'alphabet';
    state.cursor = 0;
    $app.innerHTML = `
        <div class="alphabet">
            <h2>Künstler A–Z</h2>
            <div class="hint">Buchstabe wählen</div>
            <div class="letter-grid">
                ${LETTERS.map((L, i) => `
                    <div class="letter ${i === state.cursor ? 'selected' : ''}">
                        ${L}
                    </div>`).join('')}
            </div>
        </div>`;
}
function paintAlphabet() {
    document.querySelectorAll('.alphabet .letter').forEach((el, i) =>
        el.classList.toggle('selected', i === state.cursor));
}

async function showLetterResults(letter) {
    pushBC('alphabet');
    showLoading(`Künstler mit „${letter}" werden geladen …`);
    let artists;
    try { artists = await allArtists(); }
    catch (e) { return showError(`WikiArt: ${e.message}`); }

    const L = letter.toUpperCase();
    const matches = artists
        .filter(a => firstLetter(a.name) === L)
        .sort((a, b) => a.name.localeCompare(b.name, 'de'));

    if (!matches.length) {
        return showError(`Keine Künstler für „${letter}" gefunden.`);
    }
    showList(`Künstler — ${L}`,
        matches.map(a => ({
            label: a.name,
            sub:   a.lifespan || '',
        })),
        idx => slideshowFromArtist(matches[idx])
    );
}

function firstLetter(name) {
    // Sortierung nach Nachname → letztes Wort.
    const parts = (name || '').trim().split(/\s+/);
    const last = parts[parts.length - 1] || '';
    return last.charAt(0).toUpperCase();
}

// ────── Kunstbewegungen (Künstler-fokussiert) ──────────────────────
async function showMovementCategories() {
    pushBC('menu');
    showLoading('Kunstbewegungen werden geladen …');
    let tree;
    try { tree = await artMovementsTree(); }
    catch (e) { return showError(`WikiArt: ${e.message}`); }

    const items = tree.map(c => ({
        label: c.title || c.title_en,
        sub: `${c.movements.length} Bewegungen`,
    }));
    showList('Kunstbewegungen', items,
        idx => showMovementsInCategory(tree[idx])
    );
}

function showMovementsInCategory(cat) {
    pushBC('list');
    const items = cat.movements.map(m => ({
        label: m.title,
        sub:   `${m.count} Künstler`,
    }));
    showList(cat.title || cat.title_en, items,
        idx => showMovementSubmenu(cat.movements[idx])
    );
}

function showMovementSubmenu(movement) {
    pushBC('list');
    showList(movement.title, [
        { label: '⚡ Zufall — alle Werke', isShuffle: true },
        { label: '☰ Künstler-Liste',      isShuffle: false },
    ], idx => {
        if (idx === 0) slideshowFromCategory('style', movement.slug, movement.title);
        else            showArtistsInMovement(movement);
    });
}

async function showArtistsInMovement(movement) {
    pushBC('list');
    showLoading(`${movement.title} — Künstler werden geladen …`);
    let artists;
    try { artists = await artistsByMovement(movement.slug); }
    catch (e) { return showError(`WikiArt: ${e.message}`); }
    if (!artists.length) {
        return showError(`Keine Künstler für ${movement.title}.`);
    }
    artists.sort((a, b) => a.name.localeCompare(b.name, 'de'));
    showList(movement.title,
        artists.map(a => ({ label: a.name, sub: a.lifespan || '' })),
        idx => slideshowFromArtist(artists[idx])
    );
}

// ────── Genres (60 flach) ───────────────────────────────────────────
async function showGenres() {
    pushBC('menu');
    showLoading('Genres werden geladen …');
    let genres;
    try { genres = await genresList(); }
    catch (e) { return showError(`WikiArt: ${e.message}`); }
    showList('Genres',
        genres.map(g => ({ label: g.title, sub: `${g.count} Künstler` })),
        idx => showGenreSubmenu(genres[idx])
    );
}

function showGenreSubmenu(genre) {
    pushBC('list');
    showList(genre.title, [
        { label: '⚡ Zufall — alle Werke', isShuffle: true },
        { label: '☰ Künstler-Liste',      isShuffle: false },
    ], idx => {
        if (idx === 0) slideshowFromCategory('genre', genre.slug, genre.title);
        else            showArtistsInGenre(genre);
    });
}

async function showArtistsInGenre(genre) {
    pushBC('list');
    showLoading(`${genre.title} — Künstler werden geladen …`);
    let artists;
    try { artists = await artistsByGenre(genre.slug); }
    catch (e) { return showError(`WikiArt: ${e.message}`); }
    if (!artists.length) {
        return showError(`Keine Künstler für ${genre.title}.`);
    }
    artists.sort((a, b) => a.name.localeCompare(b.name, 'de'));
    showList(genre.title,
        artists.map(a => ({ label: a.name, sub: a.lifespan || '' })),
        idx => slideshowFromArtist(artists[idx])
    );
}

// ────── Stile (Werk-fokussiert, direkte Diashow) ───────────────────
async function showStyleCategories() {
    pushBC('menu');
    showLoading('Stile werden geladen …');
    let tree;
    try { tree = await artMovementsTree(); }
    catch (e) { return showError(`WikiArt: ${e.message}`); }
    const items = tree.map(c => ({
        label: c.title || c.title_en,
        sub: `${c.movements.length} Stile`,
    }));
    showList('Stile', items, idx => showStylesInCategory(tree[idx]));
}

function showStylesInCategory(cat) {
    pushBC('list');
    const items = cat.movements.map(m => ({
        label: m.title,
        sub:   `${m.count} Künstler`,
    }));
    showList(cat.title || cat.title_en, items, idx => {
        const m = cat.movements[idx];
        slideshowFromCategory('style', m.slug, m.title);
    });
}

// ────── Themen (kuratierte Tags, direkte Diashow) ──────────────────
function showTags() {
    pushBC('menu');
    showList('Themen',
        TAGS.map(t => ({ label: t.label })),
        idx => slideshowFromTag(TAGS[idx])
    );
}

// ────── Einstellungen ───────────────────────────────────────────────
function showSettings() {
    pushBC('menu');
    state.view = 'settings';
    state.cursor = 0;
    renderSettings();
}
function renderSettings() {
    const s = loadSettings();
    const mattingHex = s.mattingColor;
    const mattingLabel = (MATTING_COLORS.find(c => c.hex === mattingHex) || {}).label || mattingHex;
    state.settingsItems = [
        // ─── Diashow ───────────────────────────────────────────────
        { label: 'Anzeigedauer pro Bild',
          value: `${s.slideDurationSec}s`,
          toggle: () => cycleList('slideDurationSec', SLIDE_DURATIONS) },
        { label: 'OSD-Anzeigedauer',
          value: s.osdHideAfterSec === 0 ? 'immer' : `${s.osdHideAfterSec}s`,
          toggle: () => cycleList('osdHideAfterSec', OSD_DURATIONS) },
        { label: 'Bildanpassung',
          value: s.imageFit === 'cover' ? 'Bildschirm füllen (croppt)' : 'Ganzes Bild (mit Rändern)',
          toggle: () => cycleList('imageFit', IMAGE_FITS) },
        // ─── Passepartout ──────────────────────────────────────────
        { label: 'Passepartout (Rahmen statt Schwarz)',
          value: s.mattingEnabled ? 'an' : 'aus',
          toggle: () => saveSettings({ mattingEnabled: !s.mattingEnabled }) },
        { label: 'Passepartout-Farbe',
          value: mattingLabel,
          swatch: mattingHex,
          toggle: () => cycleMattingColor() },
        // ─── Auto-Boot / Sleep ────────────────────────────────────
        { label: 'Auto-Boot (letzte Auswahl resumen)',
          value: s.autoBoot ? 'an' : 'aus',
          toggle: () => saveSettings({ autoBoot: !s.autoBoot }) },
        { label: 'Bildschirm-Ruhe',
          value: s.sleepEnabled ? 'an' : 'aus',
          toggle: () => saveSettings({ sleepEnabled: !s.sleepEnabled }) },
        { label: 'Ruhe von',
          value: s.sleepFrom,
          toggle: () => cycleList('sleepFrom', TIMES) },
        { label: 'Ruhe bis',
          value: s.sleepTo,
          toggle: () => cycleList('sleepTo', TIMES) },
        // ─── Reset-Aktionen ────────────────────────────────────────
        { label: 'Letzte Auswahl löschen',
          value: s.lastNav ? s.lastNav.label || s.lastNav.kind : '—',
          toggle: () => saveSettings({ lastNav: null }) },
        { label: 'Format zurücksetzen',
          value: s.orient || '—',
          toggle: () => saveSettings({ orient: null }) },
        { label: 'Favoriten',
          value: `${loadFavorites().length} gespeichert`,
          toggle: () => {
              if (!confirm('Alle Favoriten löschen?')) return;
              saveFavorites([]);
              openFavDb().then(db => db.transaction(IDB_STORE, 'readwrite').objectStore(IDB_STORE).clear());
          } },
        // ─── Pi-Steuerung ──────────────────────────────────────────
        { label: 'Pi neu starten',     value: '⏎ ausführen', toggle: () => rebootPi() },
        { label: 'Pi herunterfahren',  value: '⏎ ausführen', toggle: () => shutdownPi() },
    ];
    $app.innerHTML = `
        <div class="menu">
            <h2>Einstellungen</h2>
            ${state.settingsItems.map((it, i) => `
                <div class="menu-item ${i === state.cursor ? 'selected' : ''}">
                    ${escape(it.label)}
                    <span class="count">
                        ${it.swatch
                            ? `<span class="swatch" style="background:${escape(it.swatch)}"></span>`
                            : ''}
                        ${escape(it.value)}
                    </span>
                </div>`).join('')}
        </div>`;
}

function cycleList(field, options) {
    const s = loadSettings();
    const cur = s[field];
    const i = options.indexOf(cur);
    const next = options[(i + 1) % options.length];
    saveSettings({ [field]: next });
    applyVisualSettings();   // sofortige Wirkung wenn moeglich
}

function cycleMattingColor() {
    const s = loadSettings();
    const i = MATTING_COLORS.findIndex(c => c.hex === s.mattingColor);
    const next = MATTING_COLORS[(i + 1) % MATTING_COLORS.length];
    saveSettings({ mattingColor: next.hex });
    applyVisualSettings();
}

async function rebootPi() {
    try { await fetch('http://127.0.0.1:8787/reboot', { method: 'POST', mode: 'no-cors' }); } catch {}
}
async function shutdownPi() {
    try { await fetch('http://127.0.0.1:8787/shutdown', { method: 'POST', mode: 'no-cors' }); } catch {}
}

// ────── Favoriten — Metadata in localStorage, Bilder als Blob in IDB ─
const FAV_KEY  = 'artframe.favs';
const IDB_NAME = 'artframe-fav';
const IDB_STORE = 'images';

function loadFavorites() {
    try { return JSON.parse(localStorage.getItem(FAV_KEY) || '[]'); }
    catch { return []; }
}
function saveFavorites(list) {
    localStorage.setItem(FAV_KEY, JSON.stringify(list));
}
function favKey(item) {
    // contentId ist die WikiArt-eindeutige ID. Falls die fehlt (Mehr-
    // viewed-Liste hat sie manchmal nicht), nehmen wir Bild-URL.
    return item.contentId || item.image;
}

function openFavDb() {
    return new Promise((resolve, reject) => {
        const r = indexedDB.open(IDB_NAME, 1);
        r.onupgradeneeded = e => e.target.result.createObjectStore(IDB_STORE);
        r.onsuccess = e => resolve(e.target.result);
        r.onerror = () => reject(r.error);
    });
}
async function idbPut(key, blob) {
    const db = await openFavDb();
    return new Promise((res, rej) => {
        const tx = db.transaction(IDB_STORE, 'readwrite');
        tx.objectStore(IDB_STORE).put(blob, key);
        tx.oncomplete = res;
        tx.onerror = () => rej(tx.error);
    });
}
async function idbGet(key) {
    const db = await openFavDb();
    return new Promise((res, rej) => {
        const tx = db.transaction(IDB_STORE, 'readonly');
        const req = tx.objectStore(IDB_STORE).get(key);
        req.onsuccess = () => res(req.result || null);
        req.onerror = () => rej(req.error);
    });
}
async function idbDelete(key) {
    const db = await openFavDb();
    return new Promise((res, rej) => {
        const tx = db.transaction(IDB_STORE, 'readwrite');
        tx.objectStore(IDB_STORE).delete(key);
        tx.oncomplete = res;
        tx.onerror = () => rej(tx.error);
    });
}

async function addCurrentToFavorites() {
    const ss = state.slideshow;
    if (!ss) return;
    const it = ss.items[ss.index];
    if (!it) return;
    const k = favKey(it);
    const favs = loadFavorites();
    if (favs.find(f => favKey(f) === k)) {
        flashOsd('★ schon in Favoriten');
        return;
    }
    flashOsd('★ Speichere …');
    // Bild herunterladen + als Blob in IDB ablegen (offline-faehig).
    const url = hdUrl(it.image);
    let downloaded = false;
    try {
        const r = await fetch(url);
        if (r.ok) {
            const blob = await r.blob();
            await idbPut(k, blob);
            downloaded = true;
        }
    } catch (e) { /* CORS / Netz weg → trotzdem Metadaten speichern */ }

    favs.push({
        contentId:    it.contentId || null,
        title:        it.title || '',
        title_en:     it.title_en || '',
        title_de:     it.title_de || '',
        artistName:   it.artistName || '',
        yearAsString: it.yearAsString || '',
        image:        url,
        width:        it.width,
        height:       it.height,
        offline:      downloaded,
    });
    saveFavorites(favs);
    flashOsd(downloaded ? '★ Favorit gespeichert (offline)' : '★ Favorit gespeichert');
}

async function removeCurrentFromFavorites() {
    const ss = state.slideshow;
    if (!ss) return;
    const it = ss.items[ss.index];
    if (!it) return;
    const k = favKey(it);
    const favs = loadFavorites().filter(f => favKey(f) !== k);
    saveFavorites(favs);
    try { await idbDelete(k); } catch {}
    flashOsd('☆ Favorit entfernt');
}

function flashOsd(text) {
    const $osd = document.getElementById('osd');
    if (!$osd) return;
    $osd.innerHTML = `<div class="slideshow-title">${escape(text)}</div>`;
    $osd.classList.remove('hidden');
    clearTimeout(state.slideshow?.hideTimer);
    state.slideshow.hideTimer = setTimeout(() => $osd.classList.add('hidden'), 2500);
}

async function slideshowFavorites() {
    pushBC('menu');
    showLoading('Favoriten werden geladen …');
    const favs = loadFavorites();
    if (!favs.length) return showError('Keine Favoriten gespeichert.\nLanger Druck auf OK in der Diashow legt eins an.');
    // Offline-Bilder als Blob-URL einbinden
    const items = await Promise.all(favs.map(async f => {
        if (!f.offline) return { ...f };
        try {
            const blob = await idbGet(favKey(f));
            if (blob) return { ...f, image: URL.createObjectURL(blob) };
        } catch {}
        return { ...f };  // Fallback Online-URL
    }));
    const filtered = filterOrientation(items, state.orientation);
    if (!filtered.length) return showError('Keine Favoriten im aktuellen Format.');
    shuffle(filtered);
    saveLastNav({ kind: 'favorites' });
    startSlideshow(filtered);
}

// ────── Slideshow drivers ──────────────────────────────────────────
async function slideshowFromArtist(artist) {
    pushBC('list');
    showLoading(`${artist.name} …`);
    let paintings;
    try { paintings = await paintingsBilingual(artist.slug); }
    catch (e) { return showError(`WikiArt: ${e.message}`); }
    const filtered = filterOrientation(paintings, state.orientation);
    if (!filtered.length) {
        return showError(`Keine ${state.orientation === 'portrait' ? 'Hoch-' : 'Quer-'}format-Werke für ${artist.name}.`);
    }
    shuffle(filtered);
    saveLastNav({ kind: 'artist', slug: artist.slug, label: artist.name });
    startSlideshow(filtered);
}

async function slideshowFromCategory(kind, slug, label) {
    pushBC('list');
    showLoading(`${label} — Werke werden geladen …`);
    let paintings;
    try {
        paintings = kind === 'genre'
            ? await paintingsByGenre(slug, 10)
            : await paintingsByStyle(slug, 10);
    } catch (e) { return showError(`WikiArt: ${e.message}`); }
    const filtered = filterOrientation(paintings, state.orientation);
    if (!filtered.length) return showError(`Keine passenden Werke für ${label}.`);
    shuffle(filtered);
    saveLastNav({ kind, slug, label });
    startSlideshow(filtered);
}

async function slideshowFromTag(tag) {
    pushBC('list');
    showLoading(`${tag.label} — Werke werden geladen …`);
    let paintings;
    try { paintings = await paintingsByTag(tag.slug, 10); }
    catch (e) { return showError(`WikiArt: ${e.message}`); }
    const filtered = filterOrientation(paintings, state.orientation);
    if (!filtered.length) return showError(`Keine passenden Werke für ${tag.label}.`);
    shuffle(filtered);
    saveLastNav({ kind: 'tag', slug: tag.slug, label: tag.label });
    startSlideshow(filtered);
}

async function slideshowPopular() {
    pushBC('menu');
    showLoading('Beliebte Werke …');
    let popular;
    try { popular = await mostViewedPaintings(1, 100); }
    catch (e) { return showError(`WikiArt: ${e.message}`); }
    const adapted = (popular || []).map(p => ({
        ...p, title_en: p.title || '', title_de: '',
    }));
    const filtered = filterOrientation(adapted, state.orientation);
    if (!filtered.length) return showError('Keine passenden Werke.');
    shuffle(filtered);
    saveLastNav({ kind: 'popular' });
    startSlideshow(filtered);
}

async function slideshowRandomArtist() {
    pushBC('menu');
    showLoading('Zufälliger Künstler …');
    let artists;
    try { artists = await allArtists(); }
    catch (e) { return showError(`WikiArt: ${e.message}`); }
    if (!artists.length) return showError('Künstler-Index leer.');
    const a = artists[Math.floor(Math.random() * artists.length)];
    state.breadcrumb.pop();
    saveLastNav({ kind: 'random' });
    return slideshowFromArtist(a);
}

function saveLastNav(nav) { saveSettings({ lastNav: nav }); }

// ────── Generic list view ──────────────────────────────────────────
function showList(title, items, onSelect) {
    state.view = 'list';
    state.cursor = 0;
    state.list = { title, items, onSelect };
    renderList();
}
function renderList() {
    const { title, items } = state.list;
    const crumb = state.listStack.map(l => l.title).filter(Boolean).join(' › ');
    $app.innerHTML = `
        <div class="list">
            <div class="list-left">
                <div class="crumb">${escape(crumb)}</div>
                <h3>${escape(title)}</h3>
                <div class="list-items">
                    ${items.map((it,i) => `
                        <div class="list-item ${i === state.cursor ? 'selected' : ''}">
                            ${escape(it.label)}
                            ${it.sub ? `<span class="sub">${escape(it.sub)}</span>` : ''}
                        </div>`).join('')}
                </div>
            </div>
            <div class="list-right" id="preview"></div>
        </div>`;
}
function paintList() {
    const items = document.querySelectorAll('.list .list-item');
    items.forEach((el, i) => el.classList.toggle('selected', i === state.cursor));
    items[state.cursor]?.scrollIntoView({ block: 'nearest' });
}

// ────── Slideshow rendering ────────────────────────────────────────
let activeSlot = 'a';
let loadToken = 0;

function startSlideshow(items) {
    state.view = 'slideshow';
    state.slideshow = {
        items, index: 0,
        paused: false,
        timer: null, hideTimer: null,
    };
    $app.innerHTML = `
        <div class="slideshow">
            <div class="img" id="img-a"></div>
            <div class="img" id="img-b"></div>
            <div class="slideshow-osd hidden" id="osd"></div>
        </div>`;
    activeSlot = 'a';
    loadToken = 0;
    applyVisualSettings();
    renderSlide(0);
    scheduleNext();
}

// Wendet Settings (imageFit, Passepartout-Farbe) auf Diashow-DOM an.
// Wird beim Slideshow-Start UND bei jedem Settings-Cycle aufgerufen,
// damit Aenderungen im Einstellungs-Menue sofort sichtbar werden.
function applyVisualSettings() {
    const s = loadSettings();
    const bg = s.mattingEnabled ? s.mattingColor : '#000';
    const fit = s.imageFit === 'cover' ? 'cover' : 'contain';
    document.documentElement.style.setProperty('--matting-bg', bg);
    document.documentElement.style.setProperty('--image-fit', fit);
}

function renderSlide(idx) {
    const ss = state.slideshow;
    if (!ss) return;
    const it = ss.items[idx];
    if (!it) return;
    const url = hdUrl(it.image);
    const myToken = ++loadToken;

    const img = new Image();
    img.onload = () => {
        if (myToken !== loadToken || state.view !== 'slideshow') return;
        const nextSlot = activeSlot === 'a' ? 'b' : 'a';
        const $next = document.getElementById('img-' + nextSlot);
        const $cur  = document.getElementById('img-' + activeSlot);
        $next.style.backgroundImage = `url("${url}")`;
        $next.classList.add('visible');
        $cur?.classList.remove('visible');
        activeSlot = nextSlot;
        updateOsd(it);
        preloadAhead(idx);
    };
    img.onerror = () => {
        if (myToken === loadToken) nextSlide();
    };
    img.src = url;
}

// Laedt die naechsten 10 Bilder in den Browser-Cache, damit der
// nachfolgende Slide ohne Netzlatenz erscheint.
const _preloaded = new Set();
function preloadAhead(idx) {
    const ss = state.slideshow;
    if (!ss) return;
    const N = ss.items.length;
    for (let k = 1; k <= 10; k++) {
        const next = ss.items[(idx + k) % N];
        if (!next) continue;
        const u = hdUrl(next.image);
        if (!u || _preloaded.has(u)) continue;
        _preloaded.add(u);
        const im = new Image();
        im.src = u;
    }
}

function updateOsd(it) {
    const $osd = document.getElementById('osd');
    if (!$osd) return;
    const t_en = it.title_en || it.title || 'Ohne Titel';
    const t_de = it.title_de;
    $osd.innerHTML = `
        <div class="slideshow-title">${escape(t_en)}</div>
        ${t_de && t_de !== t_en
            ? `<div class="slideshow-title-de">${escape(t_de)}</div>` : ''}
        <div class="slideshow-artist">${escape(it.artistName || '')}</div>
        <div class="slideshow-meta">${escape(it.yearAsString || '')}</div>`;
    $osd.classList.remove('hidden');
    clearTimeout(state.slideshow.hideTimer);
    const osdSec = loadSettings().osdHideAfterSec;
    if (osdSec > 0) {
        state.slideshow.hideTimer = setTimeout(
            () => $osd.classList.add('hidden'), osdSec * 1000);
    }
}

function scheduleNext() {
    const ss = state.slideshow;
    if (!ss || ss.paused) return;
    clearTimeout(ss.timer);
    const slideMs = (loadSettings().slideDurationSec || 12) * 1000;
    ss.timer = setTimeout(() => {
        ss.index = (ss.index + 1) % ss.items.length;
        renderSlide(ss.index);
        scheduleNext();
    }, slideMs);
}
function nextSlide() {
    const ss = state.slideshow; if (!ss) return;
    ss.index = (ss.index + 1) % ss.items.length;
    renderSlide(ss.index); scheduleNext();
}
function prevSlide() {
    const ss = state.slideshow; if (!ss) return;
    ss.index = (ss.index - 1 + ss.items.length) % ss.items.length;
    renderSlide(ss.index); scheduleNext();
}
function togglePause() {
    const ss = state.slideshow; if (!ss) return;
    ss.paused = !ss.paused;
    if (ss.paused) clearTimeout(ss.timer);
    else scheduleNext();
}
function toggleOsd() {
    document.getElementById('osd')?.classList.toggle('hidden');
}
function exitSlideshow() {
    clearTimeout(state.slideshow?.timer);
    clearTimeout(state.slideshow?.hideTimer);
    state.slideshow = null;
    goBack();
}

// ────── Sleep-Timer (Bildschirm-Ruhe in der Nacht) ─────────────────
function startSleepWatcher() {
    tickSleep();
    setInterval(tickSleep, 30 * 1000);
}
function tickSleep() {
    const s = loadSettings();
    if (!s.sleepEnabled) {
        document.body.classList.remove('sleep');
        return;
    }
    const now = new Date();
    const t  = now.getHours() * 60 + now.getMinutes();
    const fr = parseHM(s.sleepFrom);
    const to = parseHM(s.sleepTo);
    const inSleep = fr < to ? (t >= fr && t < to) : (t >= fr || t < to);
    document.body.classList.toggle('sleep', inSleep);
}
function parseHM(hm) {
    const [h, m] = (hm || '00:00').split(':').map(n => +n || 0);
    return h * 60 + m;
}

// ────── Misc ────────────────────────────────────────────────────────
function pushBC(v) {
    state.breadcrumb.push(v);
    // Wenn wir gerade von einer Liste tiefer gehen, den aktuellen
    // Listen-Zustand auf den Stack legen, damit goBack() ihn restauren
    // kann. Async-Loading dazwischen verändert state.list nicht.
    if (v === 'list' && state.list && state.view === 'list') {
        state.listStack.push({ ...state.list, cursor: state.cursor });
    }
}

function goBack() {
    const prev = state.breadcrumb.pop() || 'menu';
    if (prev === 'list' && state.listStack.length) {
        const restored = state.listStack.pop();
        state.list = restored;
        state.cursor = restored.cursor || 0;
        state.view = 'list';
        renderList();
        return;
    }
    if      (prev === 'menu')     showMenu();
    else if (prev === 'alphabet') showAlphabet();
    else if (prev === 'list')     showMenu();   // kein Stack mehr → zurück ins Hauptmenü
    else                          showOrient();
}

function showLoading(msg) {
    state.view = 'loading';
    $app.innerHTML = `<div class="loading">${escape(msg)}</div>`;
}
function showError(msg) {
    state.view = 'error';
    $app.innerHTML = `
        <div class="error">${escape(msg)}<br><br>
            <span class="loading">Esc → zurück</span>
        </div>`;
}
function escape(s) {
    return String(s ?? '').replace(/[&<>"]/g,
        c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' })[c]);
}
function shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
}

// ────── Long-Press-Erkennung fuer Enter im Slideshow ────────────────
// Kurzer Druck: OSD togglen. Langer Druck (>=800ms): Favorit anlegen.
let _lpTimer = null;
let _lpFired = false;
function handleEnterKeyDown() {
    if (_lpTimer || _lpFired) return;   // bereits am laufen / schon ausgeloest
    _lpTimer = setTimeout(() => {
        _lpFired = true;
        _lpTimer = null;
        addCurrentToFavorites();
    }, 800);
}
document.addEventListener('keyup', e => {
    if (e.key !== 'Enter') return;
    if (_lpTimer) {
        clearTimeout(_lpTimer);
        _lpTimer = null;
        if (state.view === 'slideshow') toggleOsd();   // war kurzer Druck
    }
    _lpFired = false;
});

// ────── Keyboard ────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
    const k = e.key;
    e.preventDefault?.();

    // Tastendruck im Sleep-Modus weckt für die nächste Tick-Runde auf,
    // indem wir die Klasse manuell entfernen. Wenn wir noch im Sleep-
    // Fenster sind, kommt sie nach 30s wieder — passt für TV-Aufwachen.
    if (document.body.classList.contains('sleep')) {
        document.body.classList.remove('sleep');
        return;
    }

    switch (state.view) {
        case 'orient':
            if (k === 'ArrowLeft' || k === 'ArrowRight') {
                state.cursor = 1 - state.cursor; paintTiles();
            } else if (k === 'Enter' || k === ' ') {
                state.orientation =
                    document.querySelectorAll('.orient .tile')[state.cursor]
                        .dataset.orient;
                saveSettings({ orient: state.orientation });
                showMenu();
            }
            return;

        case 'menu':
            if (k === 'ArrowDown') {
                state.cursor = Math.min(state.cursor + 1, MAIN_MENU.length - 1);
                paintMenu();
            } else if (k === 'ArrowUp') {
                state.cursor = Math.max(state.cursor - 1, 0); paintMenu();
            } else if (k === 'Enter' || k === ' ') {
                MAIN_MENU[state.cursor].go();
            } else if (k === 'Escape' || k === 'Backspace') {
                showOrient();
            }
            return;

        case 'alphabet': {
            const cols = 7;
            const max = LETTERS.length - 1;
            if (k === 'ArrowRight') state.cursor = Math.min(state.cursor + 1, max);
            else if (k === 'ArrowLeft')  state.cursor = Math.max(state.cursor - 1, 0);
            else if (k === 'ArrowDown')  state.cursor = Math.min(state.cursor + cols, max);
            else if (k === 'ArrowUp')    state.cursor = Math.max(state.cursor - cols, 0);
            else if (k === 'Enter' || k === ' ') {
                showLetterResults(LETTERS[state.cursor]); return;
            } else if (k === 'Escape' || k === 'Backspace') {
                goBack(); return;
            }
            paintAlphabet();
            return;
        }

        case 'list': {
            const max = state.list.items.length - 1;
            if      (k === 'ArrowDown') state.cursor = Math.min(state.cursor + 1, max);
            else if (k === 'ArrowUp')   state.cursor = Math.max(state.cursor - 1, 0);
            else if (k === 'Enter' || k === ' ') state.list.onSelect(state.cursor);
            else if (k === 'Escape' || k === 'Backspace' || k === 'ArrowLeft') goBack();
            paintList();
            return;
        }

        case 'slideshow':
            if      (k === 'ArrowRight') nextSlide();
            else if (k === 'ArrowLeft')  prevSlide();
            else if (k === ' ')          togglePause();
            else if (k === 'i')          toggleOsd();
            else if (k === 'Enter')      handleEnterKeyDown();
            else if (k === 'f')          removeCurrentFromFavorites();   // entfernen
            else if (k === 'Escape' || k === 'Backspace') exitSlideshow();
            return;

        case 'settings': {
            const max = state.settingsItems.length - 1;
            if      (k === 'ArrowDown') state.cursor = Math.min(state.cursor + 1, max);
            else if (k === 'ArrowUp')   state.cursor = Math.max(state.cursor - 1, 0);
            else if (k === 'Enter' || k === ' ' || k === 'ArrowRight' || k === 'ArrowLeft') {
                state.settingsItems[state.cursor].toggle();
                renderSettings();
                tickSleep();
                return;
            } else if (k === 'Escape' || k === 'Backspace') {
                showMenu(); return;
            }
            renderSettings();
            return;
        }

        case 'error':
        case 'loading':
            if (k === 'Escape' || k === 'Backspace') goBack();
            return;
    }
});
