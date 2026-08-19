"""저장된 리포트를 마크다운 파일로 렌더링하고 저장한다.

이 모듈은 렌더링과 파일 쓰기만 책임진다. 리포트 조회는 storage 모듈이,
Tool 계약은 server 모듈이 담당한다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_EXPORT_DIRECTORY = "reports"


class ExportError(Exception):
    """리포트 파일을 쓰지 못했을 때 발생한다."""


def export_directory() -> Path:
    """REPORT_EXPORT_DIR 환경변수가 있으면 그 경로를, 없으면 저장소 옆의 기본 폴더를 쓴다."""

    configured = os.getenv("REPORT_EXPORT_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent / DEFAULT_EXPORT_DIRECTORY


def export_path(report_id: int) -> Path:
    """리포트 ID로 파일 경로를 정한다.

    같은 리포트는 항상 같은 파일에 쓴다. 다시 내보내면 이전 내용을 덮어쓰며,
    한 파일에 여러 리포트를 이어 붙이지 않는다.
    """

    return export_directory() / f"report-{report_id}.md"


def _table_cell(text: str) -> str:
    """마크다운 표 한 칸에 넣을 문자열을 만든다.

    표는 `|`로 칸을, 줄바꿈으로 행을 나눈다. 값에 그 두 문자가 있으면 열이
    밀리거나 행이 쪼개지므로 칸에 넣기 전에 무해하게 바꾼다.

    `|`는 백슬래시로 이스케이프하지 않고 문자 참조로 바꾼다. 값에 이미
    백슬래시가 있으면(수식 표기의 `\\|` 등) `\\\\|`가 되어 백슬래시끼리
    이스케이프를 소진하고 `|`가 다시 칸 구분자로 살아난다.

    값에 있던 백슬래시는 그에 앞서 이스케이프한다. 그대로 두면 뒤따르는
    문자 참조의 `&`를 이스케이프해 `&#124;`가 글자 그대로 보인다.
    """

    escaped = text.replace("\\", "\\\\").replace("|", "&#124;")
    for line_break in ("\r\n", "\n", "\r"):
        escaped = escaped.replace(line_break, " ")
    return escaped


def _authors_line(authors: list[str]) -> str:
    """저자가 많으면 앞의 셋만 적고 나머지는 외 N명으로 줄인다."""

    if not authors:
        return "저자 미상"
    if len(authors) <= 3:
        return ", ".join(authors)
    return f"{', '.join(authors[:3])} 외 {len(authors) - 3}명"


def _paper_link(paper: dict[str, Any]) -> str:
    """본문에서 클릭할 수 있는 출처 링크를 만든다. DOI가 있으면 DOI를 우선한다."""

    url = paper.get("doi") or paper.get("landing_page_url") or paper["openalex_url"]
    return f"[{paper['openalex_id']}]({url})"


def render(report: dict[str, Any]) -> str:
    """storage.get_report 결과를 마크다운 문서로 만든다."""

    meta = report["report"]
    findings = report["findings"]
    papers = report["papers"]
    papers_by_id = {paper["openalex_id"]: paper for paper in papers}

    lines = [
        f"# {meta['title']}",
        "",
        f"- 리포트 ID: {meta['report_id']}",
        f"- 작성 시각: {meta['created_at']}",
        f"- 연구 질문: {meta['research_question']}",
        "",
        "## 본문",
        "",
        meta["summary"],
        "",
        "## 근거와 출처",
        "",
    ]

    for finding in findings:
        # 근거가 가리키는 논문은 항상 papers에 있다. report_findings가 papers를
        # 외래 키로 참조하고, 참조 중인 논문은 삭제되지 않기 때문이다.
        paper = papers_by_id[finding["paper_openalex_id"]]
        source = f"{paper['title']} ({paper['publication_year']}) {_paper_link(paper)}"
        lines.append(f"{finding['position']}. {finding['claim']}")
        if finding["evidence"]:
            lines.append(f"   - 근거: {finding['evidence']}")
        lines.append(f"   - 출처: {source}")
        lines.append("")

    lines += ["## 참고 논문", "", "| 논문 | 연도 | 인용 | OA | 저자 |", "|---|---|---|---|---|"]
    for paper in papers:
        title = f"{_table_cell(paper['title'])} {_paper_link(paper)}"
        open_access = "O" if paper["is_open_access"] else "X"
        lines.append(
            f"| {title} | {paper['publication_year']} | "
            f"{paper['cited_by_count']} | {open_access} | "
            f"{_table_cell(_authors_line(paper['authors']))} |"
        )

    lines.append("")
    return "\n".join(lines)


def write(report: dict[str, Any]) -> Path:
    """리포트를 마크다운으로 렌더링해 파일에 쓰고 그 경로를 돌려준다."""

    path = export_path(report["report"]["report_id"])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(report), encoding="utf-8")
    except OSError as error:
        raise ExportError(str(error)) from error
    return path
