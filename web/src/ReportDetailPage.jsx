import { Link, useParams } from 'react-router-dom'

import { formatDateTime, paperUrl } from './format.js'
import { useJson } from './useJson.js'

export default function ReportDetailPage() {
  const { reportId } = useParams()
  const { status, data, error } = useJson(`/api/reports/${reportId}`)

  if (status === 'loading') {
    return <p className="notice">불러오는 중…</p>
  }
  if (status === 'failed') {
    return (
      <>
        <p className="notice notice--error">{error}</p>
        <Link className="back-link" to="/">
          ← 목록으로
        </Link>
      </>
    )
  }

  const { report, findings, papers } = data
  const papersById = new Map(papers.map((paper) => [paper.openalex_id, paper]))

  return (
    <article className="report">
      <Link className="back-link" to="/">
        ← 목록으로
      </Link>

      <h1 className="report__title">{report.title}</h1>
      <dl className="report__meta">
        <dt>작성 시각</dt>
        <dd>{formatDateTime(report.created_at)}</dd>
        <dt>연구 질문</dt>
        <dd>{report.research_question}</dd>
      </dl>

      <h2>본문</h2>
      {/* 본문은 LLM이 쓴 평문이다. 줄바꿈은 CSS로 살리고 따로 나누지 않는다. */}
      <p className="report__summary">{report.summary}</p>

      <h2>근거와 출처</h2>
      <ol className="findings">
        {findings.map((finding) => {
          // 근거가 가리키는 논문은 항상 papers에 있다. report_findings가 papers를
          // 외래 키로 참조하고, 상세 조회가 그 논문들만 골라 담기 때문이다.
          const paper = papersById.get(finding.paper_openalex_id)
          return (
            <li key={finding.position} className="finding">
              <p className="finding__claim">{finding.claim}</p>
              {finding.evidence && <p className="finding__evidence">근거: {finding.evidence}</p>}
              <p className="finding__source">
                출처:{' '}
                <a href={paperUrl(paper)} target="_blank" rel="noreferrer">
                  {paper.title} ({paper.publication_year})
                </a>
              </p>
            </li>
          )
        })}
      </ol>

      <h2>참고 논문</h2>
      <ul className="papers">
        {papers.map((paper) => (
          <li key={paper.openalex_id} className="paper">
            <a
              className="paper__title"
              href={paperUrl(paper)}
              target="_blank"
              rel="noreferrer"
            >
              {paper.title}
            </a>
            <p className="paper__meta">
              {paper.publication_year} · 인용 {paper.cited_by_count}회 ·{' '}
              {paper.is_open_access ? '오픈액세스' : '구독'}
              {paper.venue ? ` · ${paper.venue}` : ''}
            </p>
            <p className="paper__authors">
              {paper.authors.length > 0 ? paper.authors.join(', ') : '저자 미상'}
            </p>
            {paper.abstract && (
              <details className="paper__abstract">
                <summary>초록</summary>
                <p>{paper.abstract}</p>
              </details>
            )}
          </li>
        ))}
      </ul>
    </article>
  )
}
