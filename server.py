"""OpenAlex 기반 연구 지원 MCP Server.

Tool의 입출력 계약과 검증만 담당한다. OpenAlex 통신은 openalex 모듈이,
논문·리포트 보존은 storage 모듈이 책임진다.

Server는 결정적인 데이터 작업만 수행하고, 비교의 해석과 리포트 산문은 LLM이 작성한다.
"""

from __future__ import annotations

import functools
from typing import Any

from mcp.server import MCPServer

import openalex
import storage


DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100

server = MCPServer(
    name="openalex-research-assistant",
    title="OpenAlex 연구 지원",
    description=(
        "OpenAlex에서 논문을 검색·비교하고, 근거와 출처가 포함된 리포트를 "
        "SQLite에 저장·조회·삭제합니다."
    ),
)


def _tool(function):
    """Tool로 등록하면서 저장소 실패를 계약대로 error dict로 바꾼다.

    Tool은 예외를 밖으로 던지지 않는다. 저장소 실패는 어느 Tool에서나 같은 모양으로
    발생하므로 Tool마다 반복하지 않고 이 경계 한 곳에서 처리한다.
    """

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return function(*args, **kwargs)
        except storage.DatabaseError as error:
            return {"error": f"저장소에 접근하지 못했습니다: {error}"}

    return server.tool(structured_output=True)(wrapper)


def _clamp(value: int, lowest: int, highest: int) -> int:
    return max(lowest, min(value, highest))


def _normalize_ids(openalex_ids: list[str]) -> tuple[list[str], list[str]]:
    """입력 ID를 짧은 형식으로 정규화한다.

    (중복을 제거한 정규화 ID 목록, 형식이 잘못된 입력 목록)을 돌려준다.
    """

    normalized: list[str] = []
    invalid: list[str] = []

    for raw_id in openalex_ids:
        work_id = openalex.normalize_work_id(str(raw_id))
        if work_id is None:
            invalid.append(str(raw_id))
        elif work_id not in normalized:
            normalized.append(work_id)

    return normalized, invalid


# --------------------------------------------------------------------------
# 검색과 조회
# --------------------------------------------------------------------------


@_tool
def search_papers_by_title(
    title: str,
    limit: int = openalex.DEFAULT_RESULT_LIMIT,
) -> dict[str, Any]:
    """논문명을 검색어로 사용해 OpenAlex에서 특정 논문을 찾는다.

    이미 제목을 알고 있는 논문을 집어낼 때 쓴다. 연구 주제로 후보군을 넓게
    탐색할 때는 search_papers를 쓴다.

    Args:
        title: 찾고 싶은 논문의 이름 또는 제목에 포함된 검색어.
        limit: 반환할 논문 수. 기본값은 5이며 최대 25이다.
    """

    normalized_title = title.strip()
    if not normalized_title:
        return {
            "query": title,
            "error": "검색할 논문명을 입력해 주세요.",
            "papers": [],
        }

    return openalex.search_works(
        normalized_title,
        limit=_clamp(limit, 1, openalex.MAX_RESULT_LIMIT),
    )


@_tool
def search_papers(
    query: str,
    from_year: int | None = None,
    to_year: int | None = None,
    min_citations: int | None = None,
    open_access_only: bool = False,
    sort: str = "relevance",
    limit: int = openalex.DEFAULT_RESULT_LIMIT,
) -> dict[str, Any]:
    """연구 주제나 키워드로 OpenAlex에서 논문 후보군을 탐색한다.

    sort를 citations로 두면 검색어와 무관하지만 인용수가 매우 높은 논문이
    상위에 올라올 수 있다. 먼저 from_year나 min_citations로 후보를 좁힌 뒤
    인용수 정렬을 쓰는 편이 안전하다.

    초록이 없는 논문은 제목만 검색 대상이 된다. 전문 용어로만 질의하면 학회
    논문처럼 초록이 빠진 레코드를 통째로 놓치므로, from_year로 연도를 좁힌
    짧고 일반적인 질의를 함께 던져 보완한다.

    Args:
        query: 연구 질문에서 뽑아낸 주제어나 키워드.
        from_year: 이 연도 이후(해당 연도 포함)에 발행된 논문만 찾는다.
        to_year: 이 연도 이전(해당 연도 포함)에 발행된 논문만 찾는다.
        min_citations: 이 값 이상 인용된 논문만 찾는다.
        open_access_only: True이면 오픈액세스 논문만 찾는다.
        sort: 정렬 기준. relevance(관련도순, 기본값), citations(인용수순),
            recency(최신순) 중 하나.
        limit: 반환할 논문 수. 기본값은 5이며 최대 25이다.
    """

    normalized_query = query.strip()
    if not normalized_query:
        return {
            "query": query,
            "error": "검색할 주제나 키워드를 입력해 주세요.",
            "papers": [],
        }

    if sort not in openalex.SORT_OPTIONS:
        allowed = ", ".join(openalex.SORT_OPTIONS)
        return {
            "query": normalized_query,
            "error": f"sort는 {allowed} 중 하나여야 합니다. 받은 값: {sort!r}",
            "papers": [],
        }

    result = openalex.search_works(
        normalized_query,
        from_year=from_year,
        to_year=to_year,
        min_citations=min_citations,
        open_access_only=open_access_only,
        sort=sort,
        limit=_clamp(limit, 1, openalex.MAX_RESULT_LIMIT),
    )
    result["sort"] = sort
    result["filters"] = {
        "from_year": from_year,
        "to_year": to_year,
        "min_citations": min_citations,
        "open_access_only": open_access_only,
    }
    return result


@_tool
def get_paper_details(openalex_id: str) -> dict[str, Any]:
    """논문 한 편의 초록·인용수·저널·오픈액세스 여부를 OpenAlex에서 조회한다.

    Args:
        openalex_id: OpenAlex 논문 ID. W2741809807 형식과
            https://openalex.org/W2741809807 형식을 모두 받는다.
    """

    return openalex.get_work(openalex_id)


# --------------------------------------------------------------------------
# 비교
# --------------------------------------------------------------------------


@_tool
def compare_papers(openalex_ids: list[str]) -> dict[str, Any]:
    """저장된 논문들의 지표를 한 표로 모으고 집계를 계산한다.

    비교 대상은 save_papers로 미리 저장한 논문이어야 한다. 이렇게 해야 비교에
    사용한 값과 리포트가 인용할 값이 같아진다. 이 Tool은 수치만 제공하며
    해석과 결론은 제공하지 않는다.

    Args:
        openalex_ids: 비교할 논문의 OpenAlex ID 목록.
    """

    normalized_ids, invalid_ids = _normalize_ids(openalex_ids)
    if invalid_ids:
        return {
            "error": "OpenAlex 논문 ID 형식이 아닌 값이 있습니다.",
            "invalid_ids": invalid_ids,
        }
    if not normalized_ids:
        return {"error": "비교할 논문 ID를 하나 이상 입력해 주세요."}

    missing_ids = storage.find_missing_paper_ids(normalized_ids)
    if missing_ids:
        return {
            "error": "저장되지 않은 논문이 있습니다. save_papers로 먼저 저장해 주세요.",
            "missing_ids": missing_ids,
        }

    papers = storage.get_papers(normalized_ids)
    rows = [
        {
            "openalex_id": paper["openalex_id"],
            "title": paper["title"],
            "publication_year": paper["publication_year"],
            "cited_by_count": paper["cited_by_count"],
            "is_open_access": paper["is_open_access"],
            "venue": paper["venue"],
            "author_count": len(paper["authors"]),
        }
        for paper in papers
    ]

    years = [row["publication_year"] for row in rows if row["publication_year"]]
    most_cited = max(rows, key=lambda row: row["cited_by_count"] or 0)
    least_cited = min(rows, key=lambda row: row["cited_by_count"] or 0)

    return {
        "rows": rows,
        "summary": {
            "paper_count": len(rows),
            "year_range": (
                {"earliest": min(years), "latest": max(years)} if years else None
            ),
            "total_citations": sum(row["cited_by_count"] or 0 for row in rows),
            "most_cited": {
                "openalex_id": most_cited["openalex_id"],
                "title": most_cited["title"],
                "cited_by_count": most_cited["cited_by_count"],
            },
            "least_cited": {
                "openalex_id": least_cited["openalex_id"],
                "title": least_cited["title"],
                "cited_by_count": least_cited["cited_by_count"],
            },
            "open_access_count": sum(1 for row in rows if row["is_open_access"]),
        },
    }


# --------------------------------------------------------------------------
# 참고 논문 저장
# --------------------------------------------------------------------------


@_tool
def save_papers(openalex_ids: list[str]) -> dict[str, Any]:
    """참고 논문을 OpenAlex에서 가져와 초록까지 함께 저장한다.

    이미 저장된 논문은 최신 정보로 갱신한다. 비교와 리포트 작성 전에 먼저 호출한다.

    Args:
        openalex_ids: 저장할 논문의 OpenAlex ID 목록.
    """

    normalized_ids, invalid_ids = _normalize_ids(openalex_ids)
    if not normalized_ids and not invalid_ids:
        return {"error": "저장할 논문 ID를 하나 이상 입력해 주세요."}

    saved: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = [
        {"openalex_id": invalid_id, "error": "OpenAlex 논문 ID 형식이 아닙니다."}
        for invalid_id in invalid_ids
    ]

    for work_id in normalized_ids:
        result = openalex.get_work(work_id)
        if "error" in result:
            failed.append({"openalex_id": work_id, "error": result["error"]})
            continue

        paper = result["paper"]
        if not paper.get("openalex_id"):
            failed.append(
                {
                    "openalex_id": work_id,
                    "error": "OpenAlex 응답에서 논문 ID를 확인하지 못했습니다.",
                }
            )
            continue

        storage.upsert_paper(paper)
        saved.append(
            {"openalex_id": paper["openalex_id"], "title": paper["title"]}
        )

    return {"saved": saved, "saved_count": len(saved), "failed": failed}


@_tool
def list_saved_papers(limit: int = DEFAULT_LIST_LIMIT) -> dict[str, Any]:
    """저장된 참고 논문 목록을 최근 저장한 순서로 돌려준다.

    Args:
        limit: 반환할 논문 수. 기본값은 20이며 최대 100이다.
    """

    papers = storage.list_papers(_clamp(limit, 1, MAX_LIST_LIMIT))
    return {"count": len(papers), "papers": papers}


@_tool
def delete_saved_paper(openalex_id: str) -> dict[str, Any]:
    """저장된 참고 논문을 삭제한다.

    어떤 리포트의 근거로 쓰이고 있으면 출처가 끊기지 않도록 삭제를 거부한다.

    Args:
        openalex_id: 삭제할 논문의 OpenAlex ID.
    """

    work_id = openalex.normalize_work_id(openalex_id)
    if work_id is None:
        return {
            "error": "OpenAlex 논문 ID 형식이 아닙니다. 예: W2741809807",
            "deleted": False,
        }

    referencing_reports = storage.reports_referencing_paper(work_id)
    if referencing_reports:
        return {
            "error": "이 논문을 근거로 사용하는 리포트가 있어 삭제하지 않았습니다.",
            "deleted": False,
            "referenced_by": referencing_reports,
        }

    deleted = storage.delete_paper(work_id)
    if not deleted:
        return {"error": "저장된 논문에서 찾지 못했습니다.", "deleted": False}

    return {"deleted": True, "openalex_id": work_id}


# --------------------------------------------------------------------------
# 리포트
# --------------------------------------------------------------------------


def _normalize_findings(
    findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    """근거 목록을 검증하고 정규화한다. 실패하면 (None, 오류 dict)를 돌려준다."""

    normalized: list[dict[str, Any]] = []

    for position, finding in enumerate(findings, start=1):
        if not isinstance(finding, dict):
            return None, {
                "error": f"{position}번째 근거는 claim과 paper_openalex_id를 담은 객체여야 합니다."
            }

        claim = str(finding.get("claim") or "").strip()
        if not claim:
            return None, {"error": f"{position}번째 근거의 claim이 비어 있습니다."}

        raw_paper_id = str(finding.get("paper_openalex_id") or "").strip()
        paper_id = openalex.normalize_work_id(raw_paper_id) if raw_paper_id else None
        if paper_id is None:
            return None, {
                "error": (
                    f"{position}번째 근거의 paper_openalex_id가 OpenAlex 논문 ID "
                    f"형식이 아닙니다. 받은 값: {raw_paper_id!r}"
                )
            }

        evidence = finding.get("evidence")
        normalized.append(
            {
                "claim": claim,
                "evidence": str(evidence).strip() if evidence else None,
                "paper_openalex_id": paper_id,
            }
        )

    return normalized, None


@_tool
def save_report(
    title: str,
    research_question: str,
    summary: str,
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """근거와 출처가 연결된 연구 리포트를 저장한다.

    모든 주장은 저장된 논문을 출처로 지목해야 한다. 근거가 없거나 저장되지 않은
    논문을 가리키면 저장하지 않는다. 먼저 save_papers로 참고 논문을 저장한다.

    Args:
        title: 리포트 제목.
        research_question: 이 리포트가 답하려는 연구 질문.
        summary: 비교 결과를 해석한 리포트 본문. 마크다운을 써도 된다.
        findings: 주장과 출처를 짝지은 근거 목록. 각 항목은
            claim(주장, 필수), evidence(주장을 뒷받침하는 구체적 근거, 선택),
            paper_openalex_id(출처 논문의 OpenAlex ID, 필수)를 갖는다.
    """

    normalized_title = title.strip()
    normalized_question = research_question.strip()
    normalized_summary = summary.strip()

    if not normalized_title:
        return {"error": "리포트 제목을 입력해 주세요."}
    if not normalized_question:
        return {"error": "이 리포트가 답하려는 연구 질문을 입력해 주세요."}
    if not normalized_summary:
        return {"error": "리포트 본문을 입력해 주세요."}
    if not findings:
        return {
            "error": (
                "근거가 없는 리포트는 저장할 수 없습니다. 주장마다 출처 논문을 "
                "지목한 findings를 하나 이상 담아 주세요."
            )
        }

    normalized_findings, error = _normalize_findings(findings)
    if error is not None:
        return error
    assert normalized_findings is not None

    cited_ids = [finding["paper_openalex_id"] for finding in normalized_findings]
    missing_ids = storage.find_missing_paper_ids(cited_ids)
    if missing_ids:
        return {
            "error": (
                "근거가 가리키는 논문 중 저장되지 않은 것이 있습니다. "
                "save_papers로 먼저 저장해 주세요."
            ),
            "missing_ids": missing_ids,
        }

    report_id = storage.insert_report(
        normalized_title,
        normalized_question,
        normalized_summary,
        normalized_findings,
    )

    return {
        "report_id": report_id,
        "finding_count": len(normalized_findings),
        "paper_count": len(set(cited_ids)),
    }


@_tool
def list_reports(limit: int = DEFAULT_LIST_LIMIT) -> dict[str, Any]:
    """저장된 리포트 목록을 최근 저장한 순서로 돌려준다.

    Args:
        limit: 반환할 리포트 수. 기본값은 20이며 최대 100이다.
    """

    reports = storage.list_reports(_clamp(limit, 1, MAX_LIST_LIMIT))
    return {"count": len(reports), "reports": reports}


@_tool
def load_report(report_id: int) -> dict[str, Any]:
    """저장된 리포트를 본문·근거·참고 논문까지 함께 불러온다.

    Args:
        report_id: 불러올 리포트의 ID. list_reports에서 확인할 수 있다.
    """

    report = storage.get_report(report_id)
    if report is None:
        return {"error": f"{report_id}번 리포트를 찾지 못했습니다."}
    return report


@_tool
def delete_report(report_id: int) -> dict[str, Any]:
    """저장된 리포트를 삭제한다. 참고 논문은 다른 리포트에서 쓸 수 있도록 남긴다.

    Args:
        report_id: 삭제할 리포트의 ID.
    """

    deleted, deleted_findings = storage.delete_report(report_id)
    if not deleted:
        return {
            "error": f"{report_id}번 리포트를 찾지 못했습니다.",
            "deleted": False,
        }

    return {
        "deleted": True,
        "report_id": report_id,
        "deleted_findings": deleted_findings,
    }


if __name__ == "__main__":
    server.run(transport="stdio")
