// vite.config.ts

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // The Mac app renders with the system WebKit: Safari 15 on macOS 10.15.
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
  // (Optional) If you use Vitest for unit tests:
  // test: {
  //   environment: 'jsdom',
  //   setupFiles: './src/setupTests.ts',
  //   globals: true
  // },
});