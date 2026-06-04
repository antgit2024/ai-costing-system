import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import vitePluginImp from 'vite-plugin-imp'
import { visualizer } from 'rollup-plugin-visualizer'

// https://vite.dev/config/
const enableAnalyzer = process.env.ANALYZE === 'true'

export default defineConfig({
  plugins: [
    react(),
    vitePluginImp({
      libList: [
        {
          libName: 'antd',
          style: (name) => `antd/es/${name}/style/index.js`,
        },
      ],
    }),
    ...(enableAnalyzer
      ? [
          visualizer({
            filename: 'dist/stats.html',
            gzipSize: true,
            brotliSize: true,
            template: 'treemap',
          }),
        ]
      : []),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@doc': fileURLToPath(new URL('../DOC', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Allow accessing Vite dev server via public domain / IP.
    // Otherwise Vite blocks unknown Host headers.
    allowedHosts: ['work.znma.com'],
    proxy: {
      // Dev-only: proxy API calls to local backend to avoid CORS / wrong-port issues
      // when accessing the dev server from a public domain.
      '/api': {
        target: 'http://127.0.0.1:8800',
        changeOrigin: true,
      },
      // C1: 员工登录代理(POST /admin/auth/login + GET /admin/auth/me)
      '/admin/auth': {
        target: 'http://127.0.0.1:8800',
        changeOrigin: true,
      },
    },
    fs: {
      // Allow importing Markdown from repo root `DOC/` as the single source of truth
      // for in-app "guides" (shown via GuideDrawer). Without this, Vite may block
      // file access outside `frontend/`.
      allow: ['..'],
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
  },
  build: {
    rollupOptions: {
      // NOTE: revert to default chunking to avoid execution-order errors.
    },
    chunkSizeWarningLimit: 600,
  },
})
