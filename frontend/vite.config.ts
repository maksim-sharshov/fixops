import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'

// The React dashboard lives under /dashboard/, while the marketing
// landing page (repo-root index.html) is the main screen at /.
const DASHBOARD_BASE = '/dashboard/'

// In development Vite only serves the dashboard; this middleware makes
// the landing page reachable at / too, mirroring the nginx setup.
function landingPage(): Plugin {
  return {
    name: 'fixops-landing',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url === '/' || req.url === '/index.html') {
          const html = readFileSync(
            fileURLToPath(new URL('../index.html', import.meta.url)),
            'utf-8'
          )
          res.setHeader('Content-Type', 'text/html; charset=utf-8')
          res.end(html)
          return
        }
        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), landingPage()],
  base: DASHBOARD_BASE,
})
