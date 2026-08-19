"""참고 논문과 리포트를 SQLite에 보존한다.

Tool 계약이나 OpenAlex 통신은 다루지 않고 저장·조회·삭제만 책임진다.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DATABASE_NAME = "research.db"

# 저장소가 실패했을 때 Tool 경계에서 잡을 예외. 호출 측이 sqlite3를 알 필요가 없게 한다.
DatabaseError = sqlite3.Error

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    openalex_id       TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    publication_year  INTEGER,
    authors           TEXT,
    doi               TEXT,
    venue             TEXT,
    cited_by_count    INTEGER,
    is_open_access    INTEGER,
    landing_page_url  TEXT,
    abstract          TEXT,
    saved_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    title              TEXT NOT NULL,
    research_question  TEXT NOT NULL,
    summary            TEXT NOT NULL,
    created_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_findings (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id          INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    position           INTEGER NOT NULL,
    claim              TEXT NOT NULL,
    evidence           TEXT,
    paper_openalex_id  TEXT NOT NULL REFERENCES papers(openalex_id)
);

CREATE INDEX IF NOT EXISTS idx_report_findings_report
    ON report_findings(report_id);
CREATE INDEX IF NOT EXISTS idx_report_findings_paper
    ON report_findings(paper_openalex_id);
"""


def database_path() -> Path:
    """RESEARCH_DB_PATH 환경변수가 있으면 그 경로를, 없으면 저장소 옆의 기본 파일을 쓴다."""

    configured = os.getenv("RESEARCH_DB_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent / DEFAULT_DATABASE_NAME


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """호출마다 연결을 새로 연다.

    동기 Tool 함수가 별도 스레드에서 실행될 수 있어 연결을 전역으로 공유하지 않는다.
    외래 키 CASCADE는 연결마다 PRAGMA를 켜야 동작한다.
    """

    connection = sqlite3.connect(database_path())
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        yield connection
    finally:
        connection.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_paper(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "openalex_id": row["openalex_id"],
        "openalex_url": f"https://openalex.org/{row['openalex_id']}",
        "title": row["title"],
        "publication_year": row["publication_year"],
        "authors": json.loads(row["authors"]) if row["authors"] else [],
        "doi": row["doi"],
        "venue": row["venue"],
        "cited_by_count": row["cited_by_count"],
        "is_open_access": bool(row["is_open_access"]),
        "landing_page_url": row["landing_page_url"],
        "abstract": row["abstract"],
        "saved_at": row["saved_at"],
    }


def upsert_paper(paper: dict[str, Any]) -> None:
    """OpenAlex에서 가져온 논문을 저장하거나 최신 정보로 갱신한다."""

    with _connect() as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO papers (
                    openalex_id, title, publication_year, authors, doi, venue,
                    cited_by_count, is_open_access, landing_page_url, abstract, saved_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(openalex_id) DO UPDATE SET
                    title = excluded.title,
                    publication_year = excluded.publication_year,
                    authors = excluded.authors,
                    doi = excluded.doi,
                    venue = excluded.venue,
                    cited_by_count = excluded.cited_by_count,
                    is_open_access = excluded.is_open_access,
                    landing_page_url = excluded.landing_page_url,
                    abstract = excluded.abstract,
                    saved_at = excluded.saved_at
                """,
                (
                    paper["openalex_id"],
                    paper.get("title") or "",
                    paper.get("publication_year"),
                    json.dumps(paper.get("authors") or [], ensure_ascii=False),
                    paper.get("doi"),
                    paper.get("venue"),
                    paper.get("cited_by_count"),
                    int(bool(paper.get("is_open_access"))),
                    paper.get("landing_page_url"),
                    paper.get("abstract"),
                    _now(),
                ),
            )


def list_papers(limit: int) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM papers ORDER BY saved_at DESC, openalex_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_paper(row) for row in rows]


def get_papers(openalex_ids: Sequence[str]) -> list[dict[str, Any]]:
    """요청한 순서를 유지해 저장된 논문을 돌려준다. 없는 ID는 결과에서 빠진다."""

    if not openalex_ids:
        return []

    placeholders = ",".join("?" for _ in openalex_ids)
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM papers WHERE openalex_id IN ({placeholders})",
            tuple(openalex_ids),
        ).fetchall()

    papers_by_id = {row["openalex_id"]: _row_to_paper(row) for row in rows}
    return [
        papers_by_id[openalex_id]
        for openalex_id in openalex_ids
        if openalex_id in papers_by_id
    ]


def find_missing_paper_ids(openalex_ids: Sequence[str]) -> list[str]:
    """저장되지 않은 논문 ID만 입력 순서대로, 중복 없이 골라낸다."""

    unique_ids = list(dict.fromkeys(openalex_ids))
    stored = {paper["openalex_id"] for paper in get_papers(unique_ids)}
    return [openalex_id for openalex_id in unique_ids if openalex_id not in stored]


def reports_referencing_paper(openalex_id: str) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT reports.id, reports.title
            FROM reports
            JOIN report_findings ON report_findings.report_id = reports.id
            WHERE report_findings.paper_openalex_id = ?
            ORDER BY reports.id
            """,
            (openalex_id,),
        ).fetchall()
    return [{"report_id": row["id"], "title": row["title"]} for row in rows]


def delete_paper(openalex_id: str) -> bool:
    with _connect() as connection:
        with connection:
            cursor = connection.execute(
                "DELETE FROM papers WHERE openalex_id = ?", (openalex_id,)
            )
            return cursor.rowcount > 0


def insert_report(
    title: str,
    research_question: str,
    summary: str,
    findings: Sequence[dict[str, Any]],
) -> int:
    """리포트와 근거를 하나의 트랜잭션으로 저장하고 리포트 ID를 돌려준다."""

    with _connect() as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO reports (title, research_question, summary, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (title, research_question, summary, _now()),
            )
            report_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO report_findings (
                    report_id, position, claim, evidence, paper_openalex_id
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        report_id,
                        position,
                        finding["claim"],
                        finding.get("evidence"),
                        finding["paper_openalex_id"],
                    )
                    for position, finding in enumerate(findings, start=1)
                ],
            )
    return report_id


def list_reports(limit: int) -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT
                reports.id,
                reports.title,
                reports.research_question,
                reports.created_at,
                COUNT(report_findings.id) AS finding_count,
                COUNT(DISTINCT report_findings.paper_openalex_id) AS paper_count
            FROM reports
            LEFT JOIN report_findings ON report_findings.report_id = reports.id
            GROUP BY reports.id
            ORDER BY reports.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "report_id": row["id"],
            "title": row["title"],
            "research_question": row["research_question"],
            "created_at": row["created_at"],
            "finding_count": row["finding_count"],
            "paper_count": row["paper_count"],
        }
        for row in rows
    ]


def get_report(report_id: int) -> dict[str, Any] | None:
    """리포트 본문과 근거, 참고 논문을 함께 돌려준다. 없으면 None."""

    with _connect() as connection:
        report_row = connection.execute(
            "SELECT * FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        if report_row is None:
            return None

        finding_rows = connection.execute(
            """
            SELECT position, claim, evidence, paper_openalex_id
            FROM report_findings
            WHERE report_id = ?
            ORDER BY position
            """,
            (report_id,),
        ).fetchall()

        paper_rows = connection.execute(
            """
            SELECT papers.*
            FROM papers
            WHERE papers.openalex_id IN (
                SELECT DISTINCT paper_openalex_id
                FROM report_findings
                WHERE report_id = ?
            )
            ORDER BY papers.publication_year DESC, papers.openalex_id
            """,
            (report_id,),
        ).fetchall()

    return {
        "report": {
            "report_id": report_row["id"],
            "title": report_row["title"],
            "research_question": report_row["research_question"],
            "summary": report_row["summary"],
            "created_at": report_row["created_at"],
        },
        "findings": [
            {
                "position": row["position"],
                "claim": row["claim"],
                "evidence": row["evidence"],
                "paper_openalex_id": row["paper_openalex_id"],
            }
            for row in finding_rows
        ],
        "papers": [_row_to_paper(row) for row in paper_rows],
    }


def delete_report(report_id: int) -> tuple[bool, int]:
    """리포트와 근거를 지운다. 참고 논문은 남긴다.

    (삭제 여부, 함께 삭제된 근거 수)를 돌려준다.
    """

    with _connect() as connection:
        with connection:
            finding_count = connection.execute(
                "SELECT COUNT(*) FROM report_findings WHERE report_id = ?",
                (report_id,),
            ).fetchone()[0]
            cursor = connection.execute(
                "DELETE FROM reports WHERE id = ?", (report_id,)
            )
            deleted = cursor.rowcount > 0

    return deleted, finding_count if deleted else 0
