// vite.config.ts

import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The version the page sends (api.ts) is the repository's VERSION
const VERSION = readFileSync(new URL('../VERSION', import.meta.url), 'utf8').trim()

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',  // Specify output directory for build artifacts
    emptyOutDir: true,  // Remove old files before building
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  define: { __BTCTX_VERSION__: JSON.stringify(VERSION) },
});