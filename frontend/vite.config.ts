import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  test: { exclude: ['tests/e2e/**', 'node_modules/**', 'dist/**'] },
  server: { port: 5173, proxy: { '/api': 'http://localhost:10000', '/health': 'http://localhost:10000' } },
  build: {
    sourcemap: false,
    rollupOptions: { output: { manualChunks: { charts: ['recharts'], query: ['@tanstack/react-query'], ui: ['lucide-react', '@radix-ui/react-dialog'], react: ['react', 'react-dom', 'react-router-dom'] } } }
  }
})

