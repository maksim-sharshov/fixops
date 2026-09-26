import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import type { Plugin } from 'vite'

// Two pages: the landing page at / (frontend/index.html) and the React
// dashboard at /dashboard (frontend/dashboard/index.html).
function dashboardDevFallback(): Plugin {
  return {
    name: 'fixops-dashboard-fallback',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const path = (req.url ?? '').split('?')[0]
        if (
          (path === '/dashboard' || path.startsWith('/dashboard/')) &&
          !path.includes('.')
        ) {
          req.url = '/dashboard/index.html'
        }
        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), dashboardDevFallback()],
  base: '/',
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        dashboard: fileURLToPath(
          new URL('./dashboard/index.html', import.meta.url)
        ),
      },
    },
  },
})
