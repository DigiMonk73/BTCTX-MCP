// vite.config.ts

import { readFileSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The version every request names (src/api.ts) is the repository's VERSION.
// A build without it fails here, rather than make a page the server refuses.
const VERSION = readFileSync(new URL('../VERSION', import.meta.url), 'utf8').trim()

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // The Mac app renders with the system WebKit: Safari 15 (macOS 11 and later).
    // Vite 8's default target is Safari 16.4, so newer JavaScript and CSS
    // syntax would reach the page as written; this keeps both (cssTarget
    // follows target) rewritten for Safari 15.
    target: ['es2020', 'safari15'],
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