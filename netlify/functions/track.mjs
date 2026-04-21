import { getStore } from '@netlify/blobs'

const STALE_AFTER_MS = 2 * 60 * 1000

export default async (request) => {
  const store = getStore({ name: 'now-playing', consistency: 'strong' })

  if (request.method === 'GET') {
    const data = await store.get('current', { type: 'json' })
    if (!data) {
      return Response.json({ source: 'idle' })
    }
    const age = Date.now() - (data.timestamp || 0)
    if (age > STALE_AFTER_MS) {
      return Response.json({ source: 'idle', staleSince: data.timestamp })
    }
    return Response.json({ ...data, ageMs: age })
  }

  if (request.method === 'POST') {
    const secret = request.headers.get('x-relay-secret')
    const expected = Netlify.env.get('TRACK_RELAY_SECRET')
    if (!expected || secret !== expected) {
      return new Response('Unauthorized', { status: 401 })
    }

    let body
    try {
      body = await request.json()
    } catch {
      return new Response('Invalid JSON', { status: 400 })
    }

    if (body.source === 'idle') {
      await store.delete('current')
      return Response.json({ ok: true, cleared: true })
    }

    const record = {
      source: body.source || 'krp',
      title: body.title ?? null,
      artist: body.artist ?? null,
      album: body.album ?? null,
      cover: body.cover ?? null,
      station: body.station ?? null,
      stationId: body.stationId ?? null,
      timestamp: Date.now()
    }

    await store.setJSON('current', record)
    return Response.json({ ok: true, stored: record })
  }

  return new Response('Method not allowed', { status: 405 })
}

export const config = {
  path: '/api/track'
}