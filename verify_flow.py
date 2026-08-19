"""전체 연구 흐름을 한 번 실행해 보는 수동 검증 스크립트.

자동화 테스트 수트가 아니라, Tool을 순서대로 호출해 결과를 눈으로 확인하기 위한 것이다.
임시 DB를 사용하므로 실제 research.db는 건드리지 않는다.

실행:
    .\\.venv\\Scripts\\python.exe verify_flow.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any


def _configure_temporary_database() -> tempfile.TemporaryDirectory[str]:
    """DB와 리포트 내보내기 폴더를 임시 경로로 돌려 실제 작업 결과를 건드리지 않는다."""

    directory = tempfile.TemporaryDirectory()
    os.environ["RESEARCH_DB_PATH"] = str(Path(directory.name) / "verify.db")
    os.environ["REPORT_EXPORT_DIR"] = str(Path(directory.name) / "reports")
    return directory


_TEMPORARY_DIRECTORY = _configure_temporary_database()

import report_export  # noqa: E402
import server  # noqa: E402  (임시 DB 경로를 먼저 지정해야 한다)
import storage  # noqa: E402


FIXTURE_PAPERS = [
    {
        "openalex_id": "W0000000001",
        "title": "네트워크 없이 검증하기 위한 예시 논문 A",
        "publication_year": 2021,
        "authors": ["연구자 A", "연구자 B"],
        "doi": None,
        "venue": "예시 저널",
        "cited_by_count": 120,
        "is_open_access": True,
        "landing_page_url": None,
        "abstract": "오프라인 검증용 예시 초록.",
    },
    {
        "openalex_id": "W0000000002",
        "title": "네트워크 없이 검증하기 위한 예시 논문 B",
        "publication_year": 2018,
        "authors": ["연구자 C"],
        "doi": None,
        "venue": "예시 학회",
        "cited_by_count": 40,
        "is_open_access": False,
        "landing_page_url": None,
        "abstract": None,
    },
]

failures: list[str] = []
skipped: list[str] = []


def step(label: str) -> None:
    print(f"\n=== {label} ===")


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "OK  " if condition else "FAIL"
    print(f"  [{mark}] {label}{f' - {detail}' if detail else ''}")
    if not condition:
        failures.append(label)
    return condition


def preview(result: dict[str, Any], *keys: str) -> str:
    return ", ".join(f"{key}={result.get(key)!r}" for key in keys)


def _table_columns_are_uniform(markdown: str) -> bool:
    """마크다운 표의 모든 행이 같은 칸 수를 갖는지 본다.

    렌더러가 값 속 `|`를 문자 참조로 바꾸므로 표 행에 남은 `|`는 모두 칸
    구분자다. 값의 `|`가 그대로 새면 그 행만 칸이 늘어난다.
    """

    rows = [line for line in markdown.splitlines() if line.startswith("|")]
    if not rows:
        return False
    widths = {len(row.split("|")) for row in rows}
    return len(widths) == 1


def _render_with_hostile_title() -> str:
    """마크다운 구분자가 들어간 제목·저자로 리포트를 렌더링해 본다.

    OpenAlex 실제 제목에는 드물어 흐름만으로는 지나칠 수 있으므로 직접 만든다.
    맨 `|`뿐 아니라 수식 표기처럼 이미 이스케이프된 `\\|`도 함께 넣는다.
    """

    paper = {
        "openalex_id": "W0000000003",
        "openalex_url": "https://openalex.org/W0000000003",
        "title": "Bounding \\|x\\| | Attention Is All You Need\nSecond line",
        "publication_year": 2017,
        "authors": ["연구자 \\| D"],
        "doi": None,
        "venue": None,
        "cited_by_count": 1,
        "is_open_access": True,
        "landing_page_url": None,
        "abstract": None,
        "saved_at": "",
    }
    return report_export.render(
        {
            "report": {
                "report_id": 0,
                "title": "구분자 검증",
                "research_question": "표가 깨지는가?",
                "summary": "본문.",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            "findings": [
                {
                    "position": 1,
                    "claim": "주장",
                    "evidence": None,
                    "paper_openalex_id": "W0000000003",
                }
            ],
            "papers": [paper],
        }
    )


def verify_meaning_search() -> None:
    """의미 검색 Tool을 확인한다. 결과는 이후 단계로 넘기지 않는다.

    OpenAlex 베타 기능이라 간헐적으로 실패하므로, 실패를 흐름 전체의 실패로
    보지 않고 미검증으로 남긴다.
    """

    step("2. 의미로 논문 검색 (search_papers_by_meaning)")
    result = server.search_papers_by_meaning(
        "papers that use graph neural networks to discover new drugs",
        from_year=2019,
        limit=3,
    )

    if "error" in result:
        print(f"  OpenAlex 호출 실패: {result['error']}")
        print("  → 의미 검색은 OpenAlex 베타 기능이라 간헐적으로 실패한다.")
        skipped.append(f"2단계 의미 검색 (사유: {result['error']})")
        return

    papers = result["papers"]
    check("의미 검색 결과가 1건 이상", len(papers) >= 1, f"count={result.get('count')}")
    check(
        "연도 필터가 적용됨",
        all(paper["publication_year"] >= 2019 for paper in papers),
        f"from_year=2019, 결과 연도 {[paper['publication_year'] for paper in papers]}",
    )
    for paper in papers:
        print(
            f"    - {paper['openalex_id']} ({paper['publication_year']}, "
            f"인용 {paper['cited_by_count']}) {paper['title']}"
        )


def collect_paper_ids() -> list[str]:
    """OpenAlex 검색으로 논문 ID를 모은다. 실패하면 오프라인 예시로 대체한다."""

    step("1. 연구 질문으로 논문 검색 (search_papers)")
    result = server.search_papers(
        "graph neural network drug discovery",
        from_year=2019,
        min_citations=20,
        sort="relevance",
        limit=3,
    )

    if "error" in result:
        print(f"  OpenAlex 호출 실패: {result['error']}")
        print("  → 네트워크 단계는 미검증. 예시 논문으로 SQLite 계층만 검증한다.")
        skipped.append(
            "1~4단계 OpenAlex 검색·의미 검색·상세조회·저장 "
            f"(사유: {result['error']})"
        )
        for paper in FIXTURE_PAPERS:
            storage.upsert_paper(paper)
        return [paper["openalex_id"] for paper in FIXTURE_PAPERS]

    papers = result["papers"]
    check("검색 결과가 1건 이상", len(papers) >= 1, f"count={result.get('count')}")
    for paper in papers:
        print(
            f"    - {paper['openalex_id']} ({paper['publication_year']}, "
            f"인용 {paper['cited_by_count']}) {paper['title']}"
        )

    paper_ids = [paper["openalex_id"] for paper in papers]

    verify_meaning_search()

    step("3. 논문 상세 조회 (get_paper_details)")
    detail = server.get_paper_details(paper_ids[0])
    if check("상세 조회 성공", "error" not in detail, str(detail.get("error", ""))):
        abstract = detail["paper"].get("abstract")
        print(f"    초록 {'있음' if abstract else '없음(OpenAlex 미제공)'}")

    step("4. 참고 논문 저장 (save_papers)")
    saved = server.save_papers(paper_ids)
    check(
        "저장 성공 건수가 1건 이상",
        saved.get("saved_count", 0) >= 1,
        preview(saved, "saved_count"),
    )
    if saved.get("failed"):
        print(f"    실패 항목: {saved['failed']}")

    return [entry["openalex_id"] for entry in saved["saved"]] or paper_ids


def main() -> int:
    paper_ids = collect_paper_ids()

    step("5. 저장된 논문 비교 (compare_papers)")
    comparison = server.compare_papers(paper_ids)
    if check("비교 성공", "error" not in comparison, str(comparison.get("error", ""))):
        summary = comparison["summary"]
        print(
            f"    논문 {summary['paper_count']}편, 연도 {summary['year_range']}, "
            f"총 인용 {summary['total_citations']}, OA {summary['open_access_count']}편"
        )
        print(f"    최다 인용: {summary['most_cited']['title']}")

    step("6. 미저장 논문 비교 시도 (거부되어야 함)")
    rejected = server.compare_papers(["W9999999999"])
    check(
        "미저장 논문 비교 거부",
        "error" in rejected and rejected.get("missing_ids") == ["W9999999999"],
        preview(rejected, "missing_ids"),
    )

    step("7. 근거 없는 리포트 저장 시도 (거부되어야 함)")
    no_findings = server.save_report(
        title="근거 없는 리포트",
        research_question="근거가 없어도 저장될까?",
        summary="본문만 있고 근거가 없다.",
        findings=[],
    )
    check("근거 없는 리포트 거부", "error" in no_findings, str(no_findings.get("error")))

    step("8. 미저장 논문을 인용한 리포트 저장 시도 (거부되어야 함)")
    unknown_source = server.save_report(
        title="출처가 저장되지 않은 리포트",
        research_question="저장되지 않은 논문을 인용하면?",
        summary="출처가 DB에 없다.",
        findings=[
            {"claim": "저장되지 않은 논문을 근거로 든다.", "paper_openalex_id": "W9999999999"}
        ],
    )
    check(
        "미저장 출처 인용 거부",
        "error" in unknown_source and unknown_source.get("missing_ids") == ["W9999999999"],
        preview(unknown_source, "missing_ids"),
    )

    step("9. 근거와 출처를 갖춘 리포트 저장 (save_report)")
    findings = [
        {
            "claim": f"{index + 1}번째 논문이 이 연구 질문과 관련된 접근을 제시한다.",
            "evidence": "비교 표의 발행 연도와 인용수를 근거로 한다.",
            "paper_openalex_id": paper_id,
        }
        for index, paper_id in enumerate(paper_ids)
    ]
    saved_report = server.save_report(
        title="검증용 연구 리포트",
        research_question="선택한 논문들은 서로 어떻게 다른가?",
        summary="비교 표를 바탕으로 정리한 본문.",
        findings=findings,
    )
    report_saved = check(
        "리포트 저장 성공",
        "error" not in saved_report,
        preview(saved_report, "report_id", "finding_count", "paper_count"),
    )
    if not report_saved:
        return _report_result()

    report_id = saved_report["report_id"]

    step("10. 리포트 목록 조회 (list_reports)")
    listed = server.list_reports()
    check(
        "저장한 리포트가 목록에 있음",
        any(item["report_id"] == report_id for item in listed["reports"]),
        preview(listed, "count"),
    )

    step("11. 리포트 불러오기 (load_report)")
    loaded = server.load_report(report_id)
    if check("리포트 불러오기 성공", "error" not in loaded, str(loaded.get("error", ""))):
        check(
            "근거 수가 저장한 것과 일치",
            len(loaded["findings"]) == len(findings),
            f"{len(loaded['findings'])}건",
        )
        check(
            "참고 논문이 함께 조회됨",
            len(loaded["papers"]) >= 1,
            f"{len(loaded['papers'])}편",
        )
        for finding in loaded["findings"]:
            print(
                f"    {finding['position']}. {finding['claim']} "
                f"[출처 {finding['paper_openalex_id']}]"
            )

    step("12. 리포트를 마크다운으로 내보내기 (export_report)")
    exported = server.export_report(report_id)
    if check("내보내기 성공", exported.get("exported") is True, str(exported.get("error", ""))):
        exported_file = Path(exported["path"])
        first_text = exported_file.read_text(encoding="utf-8")
        check("파일이 만들어짐", exported_file.is_file(), exported["path"])
        check("본문에 리포트 제목이 있음", "검증용 연구 리포트" in first_text)
        check(
            "근거가 모두 들어감",
            all(finding["claim"] in first_text for finding in findings),
            f"{len(findings)}건",
        )

        # 다시 내보내도 같은 파일에 덮어쓰고 내용이 누적되지 않아야 한다.
        again = server.export_report(report_id)
        second_text = exported_file.read_text(encoding="utf-8")
        check("다시 내보내도 같은 경로", again.get("path") == exported["path"])
        check(
            "내용이 누적되지 않음",
            second_text == first_text and second_text.count("# 검증용 연구 리포트") == 1,
            f"{len(first_text)}자 → {len(second_text)}자",
        )
        check(
            "참고 논문 표의 열 수가 모두 같음",
            _table_columns_are_uniform(first_text),
            "제목이나 저자에 |·줄바꿈이 있어도 표가 깨지지 않아야 한다",
        )
        check(
            "제목의 |와 줄바꿈이 표를 깨지 않음",
            _table_columns_are_uniform(_render_with_hostile_title()),
            "실제 논문 제목에는 드물어 렌더링 규칙을 직접 확인한다",
        )

    step("13. 없는 리포트 내보내기 시도 (거부되어야 함)")
    missing_export = server.export_report(999999)
    check(
        "없는 리포트 내보내기 거부",
        missing_export.get("exported") is False and "error" in missing_export,
        str(missing_export.get("error", "")),
    )

    step("14. 인용 중인 논문 삭제 시도 (거부되어야 함)")
    blocked = server.delete_saved_paper(paper_ids[0])
    check(
        "인용 중인 논문 삭제 거부",
        blocked.get("deleted") is False and bool(blocked.get("referenced_by")),
        preview(blocked, "referenced_by"),
    )

    step("15. 리포트 삭제 (delete_report)")
    deleted = server.delete_report(report_id)
    check(
        "리포트 삭제 성공",
        deleted.get("deleted") is True,
        preview(deleted, "deleted_findings"),
    )
    check("삭제한 리포트는 불러올 수 없음", "error" in server.load_report(report_id))

    step("16. 리포트 삭제 후에도 참고 논문은 보존")
    remaining = server.list_saved_papers()
    check(
        "논문이 남아 있음",
        remaining["count"] >= len(paper_ids),
        preview(remaining, "count"),
    )

    step("17. 참조가 사라진 논문 삭제 (delete_saved_paper)")
    now_deletable = server.delete_saved_paper(paper_ids[0])
    check(
        "논문 삭제 성공",
        now_deletable.get("deleted") is True,
        str(now_deletable.get("error", "")),
    )

    return _report_result()


def _report_result() -> int:
    """종료 코드로 결과를 구분한다. 0=전체 통과, 1=실패, 2=일부 미검증."""

    print("\n" + "=" * 60)
    if failures:
        print(f"실패 {len(failures)}건:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    if skipped:
        print(f"실행한 단계는 모두 통과했으나 미검증 {len(skipped)}건이 남았다:")
        for item in skipped:
            print(f"  - {item}")
        return 2

    print("모든 단계 통과")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        _TEMPORARY_DIRECTORY.cleanup()
