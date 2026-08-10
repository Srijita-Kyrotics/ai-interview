import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_PROXY || 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        ws: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react-dom')) return 'vendor-react'
            if (id.includes('react-router') || id.includes('react-router-dom')) return 'vendor-router'
            if (id.includes('@codemirror') || id.includes('codemirror')) return 'vendor-codemirror'
            if (id.includes('recharts')) return 'vendor-chart'
            if (id.includes('lucide-react')) return 'vendor-lucide'
            if (id.includes('@tensorflow') || id.includes('face-api')) return 'vendor-ml'
            if (id.includes('katex')) return 'vendor-katex'
            if (id.includes('jspdf') || id.includes('html2canvas')) return 'vendor-pdf'
          }
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test-setup.js',
    css: false,
    include: ['src/**/*.{test,spec}.?(c|m)[jt]s?(x)'],
  },
})
