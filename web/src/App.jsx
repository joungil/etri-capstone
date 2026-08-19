import { Link, Route, Routes } from 'react-router-dom'

import ReportDetailPage from './ReportDetailPage.jsx'
import ReportListPage from './ReportListPage.jsx'

export default function App() {
  return (
    <div className="page">
      <header className="page__header">
        <Link className="page__home" to="/">
          연구 리포트
        </Link>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<ReportListPage />} />
          <Route path="/reports/:reportId" element={<ReportDetailPage />} />
          <Route path="*" element={<p className="notice">없는 주소입니다.</p>} />
        </Routes>
      </main>
    </div>
  )
}
