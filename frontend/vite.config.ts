import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies /api to the FastAPI backend, so the browser only ever talks to its own
// origin. Required, not just convenient: the backend sends no CORS headers (P2-55), and it
// accepts writes from Origin http://localhost:5173 only when the browser reports Sec-Fetch-Site
// same-origin, i.e. through this proxy (P2-57). Keep port 5173: the backend exception names it,
// so strictPort stops Vite from silently moving to 5174 (every write would then get a 403).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
