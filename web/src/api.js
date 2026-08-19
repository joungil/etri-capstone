// Vite 개발 서버가 /api를 web_api.py로 넘긴다. 그래서 절대 URL을 쓰지 않는다.

/** 경로 하나를 읽어 JSON을 돌려준다. 실패는 읽을 수 있는 메시지의 Error로 바꾼다. */
export async function fetchJson(path) {
  let response
  try {
    response = await fetch(path)
  } catch {
    // API가 떠 있지 않으면 fetch 자체가 실패한다. 이 경우를 구분해 주지 않으면
    // 화면에는 빈 목록만 남아 무엇이 잘못됐는지 알 수 없다.
    throw new Error('API 서버에 연결하지 못했습니다. web_api.py가 실행 중인지 확인해 주세요.')
  }

  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    // web_api.py는 실패도 error 키를 담은 JSON으로 돌려준다.
    throw new Error(payload?.error ?? `요청이 실패했습니다 (HTTP ${response.status})`)
  }
  return payload
}
