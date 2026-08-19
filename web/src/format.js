/** storage가 UTC ISO 문자열로 저장한 시각을 읽기 좋게 바꾼다. */
export function formatDateTime(isoText) {
  const parsed = new Date(isoText)
  if (Number.isNaN(parsed.getTime())) {
    return isoText
  }
  return parsed.toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' })
}

/** 출처 링크는 DOI를 우선한다. report_export의 _paper_link와 같은 규칙이다. */
export function paperUrl(paper) {
  // 빈 문자열도 걸러야 해서 ?? 대신 ||를 쓴다. 파이썬 쪽 or와 같게 동작한다.
  return paper.doi || paper.landing_page_url || paper.openalex_url
}
