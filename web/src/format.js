/** storage가 UTC ISO 문자열로 저장한 시각을 읽기 좋게 바꾼다. */
export function formatDateTime(isoText) {
  const parsed = new Date(isoText)
  if (Number.isNaN(parsed.getTime())) {
    return isoText
  }
  return parsed.toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' })
}

/** 출처 링크는 DOI를 우선한다. */
export function paperUrl(paper) {
  // 빈 문자열도 걸러야 해서 ?? 대신 ||를 쓴다.
  return paper.doi || paper.landing_page_url || paper.openalex_url
}

/** 리포트 본문을 빈 줄 기준으로 문단으로 나눈다.
 *
 * 본문은 LLM이 쓴 산문이라 빈 줄이 문단 경계다. 통째로 한 덩어리로 그리면
 * 그 경계가 그냥 빈 줄로만 보이므로, 문단마다 별도 요소로 만들어 간격을 준다.
 */
export function paragraphsOf(text) {
  return text
    .split(/\n[ \t]*\n/)
    .map((paragraph) => paragraph.trim())
    .filter((paragraph) => paragraph.length > 0)
}
