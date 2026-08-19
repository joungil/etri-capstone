import { Link } from 'react-router-dom'

import { formatDateTime } from './format.js'
import { useJson } from './useJson.js'

export default function ReportListPage() {
  const { status, data, error } = useJson('/api/reports')

  if (status === 'loading') {
    return <p className="notice">불러오는 중…</p>
  }
  if (status === 'failed') {
    return <p className="notice notice--error">{error}</p>
  }
  if (data.count === 0) {
    return (
      <p className="notice">
        저장된 리포트가 없습니다. MCP Tool <code>save_report</code>로 먼저 저장해 주세요.
      </p>
    )
  }

  return (
    <ul className="report-list">
      {data.reports.map((report) => (
        <li key={report.report_id}>
          <Link className="report-card" to={`/reports/${report.report_id}`}>
            <h2 className="report-card__title">{report.title}</h2>
            <p className="report-card__question">{report.research_question}</p>
            <p className="report-card__meta">
              {formatDateTime(report.created_at)} · 근거 {report.finding_count}건 · 참고 논문{' '}
              {report.paper_count}편
            </p>
          </Link>
        </li>
      ))}
    </ul>
  )
}
