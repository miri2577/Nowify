<template>
  <div id="app">
    <div
      v-if="player.playing"
      class="now-playing"
      :class="getNowPlayingClass()"
    >
      <div class="now-playing__cover">
        <img
          :src="player.trackAlbum.image"
          :alt="player.trackTitle"
          class="now-playing__image"
        />
      </div>
      <div class="now-playing__details">
        <h3 class="current track">Currently Playing:</h3>
        <h1 class="now-playing__track" v-text="player.trackTitle"></h1>
        <h2 class="now-playing__artists" v-text="getTrackArtists"></h2>
        <h2 class="now-playing__albums" v-text="player.trackAlbum.title"></h2>
        <h3 class="now-playing__release">Released on <span v-text="player.trackAlbum.release_date"></span> </h3>
      </div>
    </div>
    <div v-else-if="showArtwork" class="artframe-host">
      <iframe
        src="/artframe/"
        class="artframe-host__frame"
        frameborder="0"
        allow="autoplay"
        ref="artframeFrame"
      ></iframe>
    </div>
    <div v-else class="now-playing" :class="getNowPlayingClass()">
      <h1 class="now-playing__idle-heading">Waiting on a new song...</h1>
    </div>
  </div>
</template>

<script>
import * as Vibrant from 'node-vibrant'

import props from '@/utils/props.js'

const IDLE_ARTWORK_DELAY_MS = 1 * 60 * 1000
const ARTWORK_IDLE_SHUTDOWN_MS = 60 * 60 * 1000
const SHUTDOWN_ENDPOINT = 'http://127.0.0.1:8787/shutdown'

export default {
  name: 'NowPlaying',

  props: {
    auth: props.auth,
    endpoints: props.endpoints,
    player: props.player
  },

  data() {
    return {
      pollPlaying: '',
      playerResponse: {},
      playerData: this.getEmptyPlayer(),
      colourPalette: '',
      swatches: [],
      refreshing: false,
      idleSince: null,
      idleTimer: null,
      showArtwork: false,
      shutdownTimer: null
    }
  },

  computed: {
    getTrackArtists() {
      return this.player.trackArtists.join(', ')
    }
  },

  mounted() {
    this.setDataInterval()
    this.idleSince = Date.now()
    this.idleTimer = setInterval(() => this.checkIdle(), 5000)
  },

  beforeDestroy() {
    clearInterval(this.pollPlaying)
    clearInterval(this.idleTimer)
    clearTimeout(this.shutdownTimer)
  },

  methods: {
    async getRelayTrack() {
      try {
        const r = await fetch('/api/track')
        if (!r.ok) return null
        const d = await r.json()
        if (d.source !== 'krp' || !d.title) return null
        return d
      } catch (e) {
        return null
      }
    },

    async setIdleOrRelay() {
      const relay = await this.getRelayTrack()
      if (!relay) {
        this.playerData = this.getEmptyPlayer()
        return
      }
      const relayId = `relay:${relay.title}:${relay.artist || ''}`
      if (this.playerData.trackId === relayId && this.playerData.playing) {
        return
      }
      this.playerData = {
        playing: true,
        trackArtists: relay.artist ? [relay.artist] : [],
        trackTitle: relay.title,
        trackId: relayId,
        trackAlbum: {
          title: relay.album || relay.station || '',
          image: relay.cover || '',
          release_date: ''
        }
      }
    },

    async getNowPlaying() {
      let data = {}

      try {
        const response = await fetch(
          `${this.endpoints.base}/${this.endpoints.nowPlaying}`,
          {
            headers: {
              Authorization: `Bearer ${this.auth.accessToken}`
            }
          }
        )

        if (response.status === 401 || response.status === 400) {
          await this.handleExpiredToken()
          await this.setIdleOrRelay()
          return
        }

        if (!response.ok) {
          throw new Error(`An error has occured: ${response.status}`)
        }

        if (response.status === 204) {
          await this.setIdleOrRelay()
          return
        }

        data = await response.json()
        this.playerResponse = data
      } catch (error) {
        await this.setIdleOrRelay()
      }
    },

    getNowPlayingClass() {
      const playerClass = this.player.playing ? 'active' : 'idle'
      return `now-playing--${playerClass}`
    },

    getAlbumColours() {
      if (!this.player.trackAlbum?.image) {
        return
      }

      Vibrant.from(this.player.trackAlbum.image)
        .quality(1)
        .clearFilters()
        .getPalette()
        .then(palette => {
          this.handleAlbumPalette(palette)
        })
    },

    getEmptyPlayer() {
      return {
        playing: false,
        trackAlbum: {},
        trackArtists: [],
        trackId: '',
        trackTitle: ''
      }
    },

    setDataInterval() {
      clearInterval(this.pollPlaying)
      this.pollPlaying = setInterval(() => {
        this.getNowPlaying()
      }, 2500)
    },

    setAppColours() {
      document.documentElement.style.setProperty(
        '--color-text-primary',
        this.colourPalette.text
      )

      document.documentElement.style.setProperty(
        '--colour-background-now-playing',
        this.colourPalette.background
      )
    },

    handleNowPlaying() {
      if (
        this.playerResponse.error?.status === 401 ||
        this.playerResponse.error?.status === 400
      ) {
        this.handleExpiredToken()
        return
      }

      if (this.playerResponse.is_playing === false) {
        this.setIdleOrRelay()
        return
      }

      if (this.playerResponse.item?.id === this.playerData.trackId) {
        return
      }

      this.playerData = {
        playing: this.playerResponse.is_playing,
        trackArtists: this.playerResponse.item.artists.map(
          artist => artist.name
        ),
        trackTitle: this.playerResponse.item.name,
        trackId: this.playerResponse.item.id,
        trackAlbum: {
          title: this.playerResponse.item.album.name,
          image: this.playerResponse.item.album.images[0].url,
          release_date: this.playerResponse.item.album.release_date
        }
      }
    },

    handleAlbumPalette(palette) {
      let albumColours = Object.keys(palette)
        .filter(item => (item === null ? null : item))
        .map(colour => ({
          text: palette[colour].getTitleTextColor(),
          background: palette[colour].getHex()
        }))

      this.swatches = albumColours

      this.colourPalette =
        albumColours[Math.floor(Math.random() * albumColours.length)]

      this.$nextTick(() => {
        this.setAppColours()
      })
    },

    /**
     * Refresh the Spotify access token inline, without switching
     * away from this component. Runs silently.
     */
    async handleExpiredToken() {
      if (this.refreshing) return
      if (!this.auth.refreshToken) return
      this.refreshing = true
      try {
        const body = new URLSearchParams({
          grant_type: 'refresh_token',
          refresh_token: this.auth.refreshToken
        }).toString()

        const creds = btoa(`${this.auth.clientId}:${this.auth.clientSecret}`)
        const res = await fetch(`${this.endpoints.token}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            Authorization: `Basic ${creds}`
          },
          body
        })
        if (!res.ok) return
        const data = await res.json()
        if (data.access_token) {
          this.auth.accessToken = data.access_token
          if (data.refresh_token) {
            this.auth.refreshToken = data.refresh_token
          }
          this.auth.status = true
        }
      } catch (e) {
        // swallow — next poll retries
      } finally {
        this.refreshing = false
      }
    },

    /**
     * Check if enough idle time has passed to switch to artwork mode.
     */
    checkIdle() {
      if (this.playerData.playing) {
        this.idleSince = Date.now()
        if (this.showArtwork) this.exitArtwork()
        return
      }
      if (!this.idleSince) {
        this.idleSince = Date.now()
        return
      }
      const idleMs = Date.now() - this.idleSince
      if (!this.showArtwork && idleMs >= IDLE_ARTWORK_DELAY_MS) {
        this.enterArtwork()
      }
    },

    enterArtwork() {
      this.showArtwork = true
      // Iframe (Artframe-Webui) zeigt Slideshow + reagiert auf TV-Remote.
      // Fokus auf den iframe legen, damit FLIRC-Tasten ankommen.
      this.$nextTick(() => {
        this.$refs.artframeFrame?.contentWindow?.focus()
      })
      clearTimeout(this.shutdownTimer)
      this.shutdownTimer = setTimeout(
        () => this.requestShutdown(),
        ARTWORK_IDLE_SHUTDOWN_MS
      )
    },

    exitArtwork() {
      this.showArtwork = false
      clearTimeout(this.shutdownTimer)
      this.shutdownTimer = null
    },

    requestShutdown() {
      // Fire-and-forget to Pi-local helper daemon. If the daemon is not
      // running (e.g. during local dev), the fetch fails silently.
      try {
        fetch(SHUTDOWN_ENDPOINT, { method: 'POST', mode: 'no-cors' }).catch(
          () => {}
        )
      } catch (e) {
        // ignore
      }
    },

  },

  watch: {
    auth: function(oldVal, newVal) {
      if (newVal.status === false) {
        // Do not tear down the poll — we refresh inline now.
      }
    },

    playerResponse: function() {
      this.handleNowPlaying()
    },

    playerData: function() {
      this.$emit('spotifyTrackUpdated', this.playerData)

      if (this.playerData.playing) {
        this.idleSince = Date.now()
        if (this.showArtwork) this.exitArtwork()
      }

      this.$nextTick(() => {
        this.getAlbumColours()
      })
    }
  }
}
</script>

<style src="@/styles/components/now-playing.scss" lang="scss" scoped></style>

<style lang="scss" scoped>
.artframe-host {
  position: fixed;
  inset: 0;
  background: #0a0a0a;
  margin: 0;
  padding: 0;
  overflow: hidden;

  &__frame {
    width: 100vw;
    height: 100vh;
    border: 0;
    display: block;
  }
}
</style>
