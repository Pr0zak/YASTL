import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../app/static/dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/thumbnails': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
})
