import { Link, useParams } from 'react-router-dom'

import { formatDateTime, paperUrl, paragraphsOf } from './format.js'
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
        <div className="panel panel--prose">
          {paragraphsOf(report.summary).map((paragraph, index) => (
            <p key={index} className="prose">
              {paragraph}
            </p>
          ))}
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
        <PapersTable papers={papers} />
      </section>
    </article>
  )
}

/* 지표는 나란히 놓고 비교하는 값이라 표로 읽는 편이 빠르다. 열이 좁아지면
   표만 가로로 스크롤하고 페이지 자체는 밀리지 않는다. */
function PapersTable({ papers }) {
  return (
    <div className="panel table-wrap">
      <table className="table">
        <caption className="table__caption">
          인용수는 저장 시점의 값이다. 제목을 누르면 원문으로 이동한다.
        </caption>
        <thead>
          <tr>
            <th scope="col">논문</th>
            <th scope="col" className="table__number">
              연도
            </th>
            <th scope="col" className="table__number">
              인용
            </th>
            <th scope="col" className="table__center">
              오픈액세스
            </th>
            <th scope="col">저자</th>
          </tr>
        </thead>
        <tbody>
          {papers.map((paper) => (
            <tr key={paper.openalex_id}>
              <th scope="row" className="table__paper">
                <a
                  className="paper__title"
                  href={paperUrl(paper)}
                  target="_blank"
                  rel="noreferrer"
                >
                  {paper.title}
                </a>
                {paper.venue && <p className="paper__venue">{paper.venue}</p>}
                {paper.abstract && (
                  <details className="abstract">
                    <summary className="abstract__summary">초록</summary>
                    <p className="abstract__body">{paper.abstract}</p>
                  </details>
                )}
              </th>
              <td className="table__number">{paper.publication_year}</td>
              <td className="table__number">{paper.cited_by_count}</td>
              <td className="table__center">
                {paper.is_open_access ? (
                  <span className="badge badge--open">예</span>
                ) : (
                  <span className="badge">아니오</span>
                )}
              </td>
              <td className="table__authors">
                {paper.authors.length > 0 ? paper.authors.join(', ') : '저자 미상'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BackLink() {
  return (
    <Link className="back" to="/">
      <span aria-hidden="true">‹</span> 목록
    </Link>
  )
}
