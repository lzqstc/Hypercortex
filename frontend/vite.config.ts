import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import checker from 'vite-plugin-checker'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    checker({
      // 项目用 project references，根 tsconfig 的 files 为空，需指向 app 配置
      typescript: { tsconfigPath: 'tsconfig.app.json' },
      overlay: {
        // 左下角角标 + 错误面板，出现 error 时自动展开
        position: 'bl',
        initialIsOpen: 'error',
        // 右侧留出自定义常驻徽标的位置，避免两者重叠
        badgeStyle: 'left: 120px;',
      },
      terminal: true,
    }),
  ],
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  server: {
    host: '127.0.0.1',
    port: 8000,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
