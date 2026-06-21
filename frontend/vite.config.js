import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/setup': 'http://localhost:8000',
      '/process-emails': 'http://localhost:8000',
      '/logout': 'http://localhost:8000',
      '/static': 'http://localhost:8000',
      '/profile': 'http://localhost:8000',
    },
  },
})
