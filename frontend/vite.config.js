import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const proxy = {
  '/api': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:5000' },
}

export default defineConfig({
  plugins: [vue()],
  server: { host: 'localhost', port: 5173, strictPort: true, proxy },
  preview: { host: 'localhost', proxy },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const packagePath = id.replaceAll('\\', '/')
          if (packagePath.includes('/node_modules/zrender/')) return 'chart-renderer'
          if (packagePath.includes('/node_modules/echarts/')) return 'echarts'
        },
      },
    },
  },
})
