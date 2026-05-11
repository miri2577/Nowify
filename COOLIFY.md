# Nowify auf Coolify deployen

Diese `coolify`-Branch enthält alles für ein Self-Hosting via Coolify/Docker —
als Ersatz für die Netlify-Deployment.

## Was anders ist gegenüber `main`

Ein einziger Container (multi-stage Dockerfile) der:

1. Vue-SPA baut (`npm run build` + WebUI-Kopie)
2. Express-Server (`server/index.mjs`) startet, der:
   - die SPA aus `./public` serviert
   - `/api/track` 1:1 wie die Netlify-Function abbildet (File-Storage statt Netlify-Blob)
   - `/wikiart/*` + `/wikiart-img/:bucket/*` als CORS-Proxies reverse-proxified

## Required ENV-Vars (in Coolify → Application → Environment)

| Variable | Zweck |
|---|---|
| `VUE_APP_SP_CLIENT_ID` | Spotify-App Client-ID (Build-Time) |
| `VUE_APP_SP_CLIENT_SECRET` | Spotify-App Client-Secret (Build-Time) |
| `TRACK_RELAY_SECRET` | Secret für POST `/api/track` (Runtime) |

Die ersten beiden müssen **als Build-Arg** markiert sein (Coolify-UI: "Build Time").

## Persistent Volume

`/data` muss persistent gemountet sein — dort liegt `now-playing.json`.

In Coolify: Application → Storage → Mount `/data` als Volume oder Bind-Mount.

## Spotify Redirect URI

Im [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) muss
die Domain als erlaubte Redirect-URI eingetragen werden:

```
https://nowify.cavia-aperea.de
```

(zusätzlich oder anstelle der bisherigen Netlify-URL).

## Pi-Relay

Das Skript unter `pi/` schickt POSTs an `/api/track`. Die Ziel-URL im Pi muss
auf `https://nowify.cavia-aperea.de/api/track` umgestellt werden und das
`x-relay-secret`-Header passt zum `TRACK_RELAY_SECRET` oben.
