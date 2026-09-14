import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // firebase-messaging-sw.js must stay a real Flask-served JS file
      // (server-baked Firebase config, synchronous registration to avoid
      // missing an early push event — see the Flask route's own comment).
      // It has to be reachable at the SPA's own origin root for the
      // service-worker scope to include the whole site, so Vite proxies
      // this one path through to the local Flask API during dev.
      '/firebase-messaging-sw.js': 'http://localhost:5000',
    },
  },
})
