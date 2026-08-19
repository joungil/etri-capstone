import { useEffect, useState } from 'react'

import { fetchJson } from './api.js'

/** 경로 하나를 읽어 로딩·실패·완료 세 상태로 돌려준다. 목록과 상세가 함께 쓴다. */
export function useJson(path) {
  const [state, setState] = useState({ status: 'loading', data: null, error: null })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading', data: null, error: null })

    fetchJson(path).then(
      (data) => {
        if (!cancelled) setState({ status: 'ready', data, error: null })
      },
      (error) => {
        if (!cancelled) setState({ status: 'failed', data: null, error: error.message })
      },
    )

    // 목록에서 상세로 넘어가는 도중 이전 요청이 늦게 끝나면 화면이 뒤바뀐다.
    return () => {
      cancelled = true
    }
  }, [path])

  return state
}
