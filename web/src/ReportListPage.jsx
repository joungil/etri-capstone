import { Link } from 'react-router-dom'

import { formatDateTime } from './format.js'
import { useJson } from './useJson.js'

export default function ReportListPage() {
  const { status, data, error } = useJson('/api/reports')

  if (status === 'loading') {
    return <p className="notice notice--loading">불러오는 중</p>
  }
  if (status === 'failed') {
    return <p className="notice notice--error">{error}</p>
  }
  if (data.count === 0) {
    return (
      <>
        <PageHeading count={0} />
        <p className="notice">
          아직 저장된 리포트가 없습니다. MCP Tool <code>save_report</code>로 먼저 저장해
          주세요.
        </p>
      </>
    )
  }

  return (
    <>
      <PageHeading count={data.count} />
      <ul className="report-list">
        {data.reports.map((report) => (
          <li key={report.report_id}>
            <Link className="card" to={`/reports/${report.report_id}`}>
              <h2 className="card__title">{report.title}</h2>
              <p className="card__question">{report.research_question}</p>
              <p className="card__meta">
                {formatDateTime(report.created_at)}
                <span className="dot" />
                근거 {report.finding_count}건
                <span className="dot" />
                참고 논문 {report.paper_count}편
              </p>
              {/* 누를 수 있다는 신호. 장식이라 스크린리더에서 감춘다. */}
              <span className="card__chevron" aria-hidden="true">
                ›
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  )
}

function PageHeading({ count }) {
  return (
    <header className="hero">
      <h1 className="hero__title">저장된 리포트</h1>
      <p className="hero__subtitle">
        {count > 0
          ? `${count}건의 리포트를 근거와 출처와 함께 보관하고 있습니다.`
          : '리포트를 저장하면 이곳에 모입니다.'}
      </p>
    </header>
  )
}
