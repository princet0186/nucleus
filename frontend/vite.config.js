import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/triage': 'http://localhost:8800',
      '/health': 'http://localhost:8800',
      '/nucleus': 'http://localhost:8800',
      // Vector tiles arrive gzipped with Content-Encoding set by the backend;
      // the proxy must pass them through untouched or MapLibre gets garbage.
      '/maps': 'http://localhost:8800',
    }
  }
})
