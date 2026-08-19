import { Link, useParams } from 'react-router-dom'

import { formatDateTime, paperUrl } from './format.js'
import { useJson } from './useJson.js'

export default function ReportDetailPage() {
  const { reportId } = useParams()
  const { status, data, error } = useJson(`/api/reports/${reportId}`)

  if (status === 'loading') {
    return <p className="notice notice--loading">불러오는 중</p>
  }
  if (status === 'failed') {
    return (
      <>
        <BackLink />
        <p className="notice notice--error">{error}</p>
      </>
    )
  }

  const { report, findings, papers } = data
  const papersById = new Map(papers.map((paper) => [paper.openalex_id, paper]))

  return (
    <article>
      <BackLink />

      <header className="hero">
        <h1 className="hero__title">{report.title}</h1>
        <p className="hero__subtitle">{report.research_question}</p>
        <p className="hero__stamp">{formatDateTime(report.created_at)}</p>
      </header>

      <section className="section">
        <h2 className="section__heading">본문</h2>
        {/* 본문은 LLM이 쓴 평문이다. 줄바꿈은 CSS로 살리고 따로 나누지 않는다. */}
        <div className="panel panel--prose">
          <p className="prose">{report.summary}</p>
        </div>
      </section>

      <section className="section">
        <h2 className="section__heading">
          근거와 출처
          <span className="section__count">{findings.length}</span>
        </h2>
        <ol className="panel findings">
          {findings.map((finding) => {
            // 근거가 가리키는 논문은 항상 papers에 있다. report_findings가 papers를
            // 외래 키로 참조하고, 상세 조회가 그 논문들만 골라 담기 때문이다.
            const paper = papersById.get(finding.paper_openalex_id)
            return (
              <li key={finding.position} className="finding">
                <p className="finding__claim">{finding.claim}</p>
                {finding.evidence && (
                  <p className="finding__evidence">{finding.evidence}</p>
                )}
                <a
                  className="finding__source"
                  href={paperUrl(paper)}
                  target="_blank"
                  rel="noreferrer"
                >
                  {paper.title} ({paper.publication_year})
                </a>
              </li>
            )
          })}
        </ol>
      </section>

      <section className="section">
        <h2 className="section__heading">
          참고 논문
          <span className="section__count">{papers.length}</span>
        </h2>
        <ul className="panel">
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

              <p className="paper__authors">
                {paper.authors.length > 0 ? paper.authors.join(', ') : '저자 미상'}
              </p>

              <p className="paper__meta">
                <span className="badge">{paper.publication_year}</span>
                <span className="badge badge--citations">인용 {paper.cited_by_count}</span>
                {paper.is_open_access && (
                  <span className="badge badge--open">오픈액세스</span>
                )}
                {paper.venue && <span className="paper__venue">{paper.venue}</span>}
              </p>

              {paper.abstract && (
                <details className="abstract">
                  <summary className="abstract__summary">초록</summary>
                  <p className="abstract__body">{paper.abstract}</p>
                </details>
              )}
            </li>
          ))}
        </ul>
      </section>
    </article>
  )
}

function BackLink() {
  return (
    <Link className="back" to="/">
      <span aria-hidden="true">‹</span> 목록
    </Link>
  )
}
