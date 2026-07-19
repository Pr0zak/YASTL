import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
  build: {
    outDir: '../app/static/dist',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Split heavy vendor libs into their own long-lived chunks so a
        // deploy that only touches app code doesn't force browsers to
        // re-download Three.js. (Three.js is additionally behind a
        // dynamic import, so it isn't fetched until a model is opened.)
        manualChunks: {
          three: ['three'],
          vue: ['vue'],
        },
        // Timestamp only the entry filename to bust the index.html asset
        // reference on every deploy; content-hashed chunks keep their
        // names when unchanged so the browser cache survives updates.
        entryFileNames: `assets/[name]-[hash]-${Date.now()}.js`,
        chunkFileNames: `assets/[name]-[hash].js`,
        assetFileNames: `assets/[name]-[hash].[ext]`,
      },
    },
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
