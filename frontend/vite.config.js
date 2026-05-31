import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8081',
        changeOrigin: true,
        secure: false,
      },
      '/sso': {
        target: 'http://127.0.0.1:8081',
        changeOrigin: true,
        secure: false,
      }
    }
  },
  build: {
    outDir: resolve(__dirname, '../src/spectra/web/dist'),
    emptyOutDir: true,
  }
})
