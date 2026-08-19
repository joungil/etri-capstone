"""OpenAlex API 통신과 응답 정규화를 담당한다.

이 모듈은 HTTP 요청과 필드 추출만 책임지며, 저장이나 Tool 계약은 다루지 않는다.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WORKS_URL = "https://api.openalex.org/works"
USER_AGENT = "etri-capstone/1.0"
REQUEST_TIMEOUT_SECONDS = 20

DEFAULT_RESULT_LIMIT = 5
MAX_RESULT_LIMIT = 25

LIST_FIELDS = (
    "id,display_name,publication_year,doi,authorships,primary_location,"
    "cited_by_count,open_access"
)
DETAIL_FIELDS = f"{LIST_FIELDS},abstract_inverted_index"

SORT_OPTIONS = {
    "relevance": "relevance_score:desc",
    "citations": "cited_by_count:desc",
    "recency": "publication_date:desc",
}

WORK_ID_PATTERN = re.compile(r"^W\d+$")


def normalize_work_id(openalex_id: str) -> str | None:
    """`W2741809807`과 `https://openalex.org/W2741809807`을 모두 짧은 형식으로 바꾼다.

    OpenAlex 논문 ID로 해석할 수 없으면 None을 반환한다.
    """

    candidate = openalex_id.strip().rstrip("/")
    if not candidate:
        return None

    work_id = candidate.rsplit("/", 1)[-1].upper()
    if not WORK_ID_PATTERN.match(work_id):
        return None
    return work_id


def _rate_limit_message(error: HTTPError) -> str:
    """429 응답에 재시도 시점과 해결책을 덧붙인다.

    호출 측이 곧바로 재시도해도 소용없는 상황이므로 대기 시간을 함께 알린다.
    """

    parts = ["OpenAlex 요청 한도를 초과했습니다."]

    retry_after = error.headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        seconds = int(retry_after)
        if seconds >= 3600:
            parts.append(f"약 {seconds / 3600:.1f}시간 후에 초기화됩니다.")
        else:
            parts.append(f"약 {max(1, seconds // 60)}분 후에 초기화됩니다.")

    if not os.getenv("OPENALEX_API_KEY"):
        parts.append("OPENALEX_API_KEY를 설정하면 한도가 올라갑니다.")

    return " ".join(parts)


def _request(url: str) -> tuple[dict[str, Any] | None, str | None]:
    """OpenAlex에 GET 요청을 보내고 (응답, 오류 메시지) 형태로 돌려준다."""

    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.load(response), None
    except HTTPError as error:
        if error.code == 429:
            return None, _rate_limit_message(error)
        return None, f"OpenAlex가 HTTP {error.code} 응답을 반환했습니다."
    except URLError as error:
        return None, f"OpenAlex에 연결하지 못했습니다: {error.reason}"
    except OSError as error:
        # 응답 본문을 읽는 도중의 타임아웃은 URLError로 감싸이지 않고 그대로 올라온다.
        return None, f"OpenAlex 응답을 받지 못했습니다: {error}"
    except json.JSONDecodeError:
        # 장애 시 OpenAlex 앞단이 JSON 대신 HTML 오류 페이지를 돌려줄 수 있다.
        return None, "OpenAlex 응답을 JSON으로 해석하지 못했습니다."


def _with_api_key(params: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("OPENALEX_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


def _author_names(authorships: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for authorship in authorships:
        author = authorship.get("author") or {}
        name = author.get("display_name")
        if name:
            names.append(str(name))
    return names


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex의 abstract_inverted_index(단어 -> 위치 목록)를 원문 순서로 되돌린다."""

    if not inverted_index:
        return None

    positioned_words: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for position in positions:
            positioned_words.append((position, word))

    positioned_words.sort()
    return " ".join(word for _, word in positioned_words)


def _normalize_work(
    work: dict[str, Any],
    *,
    include_abstract: bool = False,
) -> dict[str, Any]:
    """OpenAlex 원본 레코드를 이 프로젝트가 쓰는 논문 표현으로 바꾼다."""

    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    open_access = work.get("open_access") or {}
    work_id = normalize_work_id(str(work.get("id") or ""))

    paper = {
        "openalex_id": work_id,
        "openalex_url": f"https://openalex.org/{work_id}" if work_id else None,
        "title": work.get("display_name"),
        "publication_year": work.get("publication_year"),
        "authors": _author_names(work.get("authorships") or []),
        "doi": work.get("doi"),
        "venue": source.get("display_name"),
        "cited_by_count": work.get("cited_by_count"),
        "is_open_access": bool(open_access.get("is_oa")),
        "landing_page_url": primary_location.get("landing_page_url"),
    }

    if include_abstract:
        paper["abstract"] = _reconstruct_abstract(work.get("abstract_inverted_index"))

    return paper


def _build_filter(
    from_year: int | None,
    to_year: int | None,
    min_citations: int | None,
    open_access_only: bool,
) -> str:
    """OpenAlex filter 파라미터를 조립한다. 조건이 없으면 빈 문자열을 돌려준다.

    OpenAlex의 `>`와 `<`는 경계값을 포함하지 않으므로 이상/이하 조건은 1을 조정한다.
    """

    conditions: list[str] = []

    if from_year is not None and to_year is not None:
        conditions.append(f"publication_year:{from_year}-{to_year}")
    elif from_year is not None:
        conditions.append(f"publication_year:>{from_year - 1}")
    elif to_year is not None:
        conditions.append(f"publication_year:<{to_year + 1}")

    if min_citations is not None and min_citations > 0:
        conditions.append(f"cited_by_count:>{min_citations - 1}")

    if open_access_only:
        conditions.append("open_access.is_oa:true")

    return ",".join(conditions)


def search_works(
    query: str,
    *,
    from_year: int | None = None,
    to_year: int | None = None,
    min_citations: int | None = None,
    open_access_only: bool = False,
    sort: str = "relevance",
    limit: int = DEFAULT_RESULT_LIMIT,
) -> dict[str, Any]:
    """검색어와 필터로 OpenAlex 논문 목록을 찾는다.

    호출 측에서 sort 값을 미리 검증해야 한다. SORT_OPTIONS에 없으면 관련도순으로 처리한다.
    """

    params: dict[str, Any] = {
        "search": query,
        "per_page": limit,
        "select": LIST_FIELDS,
        "sort": SORT_OPTIONS.get(sort, SORT_OPTIONS["relevance"]),
    }

    filter_expression = _build_filter(
        from_year, to_year, min_citations, open_access_only
    )
    if filter_expression:
        params["filter"] = filter_expression

    payload, error = _request(f"{WORKS_URL}?{urlencode(_with_api_key(params))}")
    if error is not None:
        return {"query": query, "error": error, "papers": []}

    papers = [
        _normalize_work(work) for work in (payload or {}).get("results", [])
    ]
    return {"query": query, "count": len(papers), "papers": papers}


def get_work(openalex_id: str) -> dict[str, Any]:
    """단일 논문을 초록까지 포함해 조회한다."""

    work_id = normalize_work_id(openalex_id)
    if work_id is None:
        return {
            "openalex_id": openalex_id,
            "error": "OpenAlex 논문 ID 형식이 아닙니다. 예: W2741809807",
        }

    params = _with_api_key({"select": DETAIL_FIELDS})
    payload, error = _request(f"{WORKS_URL}/{work_id}?{urlencode(params)}")
    if error is not None:
        return {"openalex_id": work_id, "error": error}

    return {"paper": _normalize_work(payload or {}, include_abstract=True)}
