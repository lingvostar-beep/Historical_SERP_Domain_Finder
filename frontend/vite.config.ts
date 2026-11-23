import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: '../app/static',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8872',
      '/health': 'http://127.0.0.1:8872',
      '/docs': 'http://127.0.0.1:8872',
      '/openapi.json': 'http://127.0.0.1:8872',
    },
  },
})
