import { Link, Route, Routes } from 'react-router-dom'

import ReportDetailPage from './ReportDetailPage.jsx'
import ReportListPage from './ReportListPage.jsx'

export default function App() {
  return (
    <>
      {/* 내비는 화면 전체 폭에 걸쳐야 뒤 내용이 지나갈 때 블러가 자연스럽다.
          그래서 가운데 정렬은 안쪽 래퍼가 맡는다. */}
      <header className="topbar">
        <nav className="topbar__inner">
          <Link className="topbar__brand" to="/">
            연구 리포트
          </Link>
        </nav>
      </header>

      <main className="main">
        <Routes>
          <Route path="/" element={<ReportListPage />} />
          <Route path="/reports/:reportId" element={<ReportDetailPage />} />
          <Route
            path="*"
            element={<p className="notice">없는 주소입니다.</p>}
          />
        </Routes>
      </main>
    </>
  )
}
