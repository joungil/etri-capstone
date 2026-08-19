import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 개발 서버는 3000에 고정한다. 다른 포트로 옮겨 열리면 확인할 주소가 달라진다.
//
// 리포트 데이터는 web_api.py가 8000에서 들고 있다. /api 요청만 그쪽으로 넘겨
// 브라우저에는 같은 출처로 보이게 하고, 그래서 API에 CORS 헤더를 두지 않는다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
