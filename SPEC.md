# OpenAlex 기반 연구 지원 MCP Server 명세

## Context

`README.md`의 실습 요구사항은 LLM이 논문을 찾고 분석·비교하며, 작성한 리포트를 저장하고 다시 활용하는 것이다. 저장소의 기존 `server.py`는 `search_papers_by_title` Tool 하나만 제공하는 참고 구현으로, MCP Server 선언·Tool 등록·OpenAlex 요청·stdio 구동 구조를 보여주는 역할까지만 한다. 비교 분석, 리포트 작성 지원, SQLite 영속화는 존재하지 않는다.

이 명세는 그 참고 구현의 패턴을 유지한 채 나머지 요구사항을 채우기 위한 것이다.

## Goal

다음 흐름을 MCP Tool 호출만으로 완주할 수 있게 한다.

```text
연구 질문
→ OpenAlex를 활용한 논문 검색
→ 연구 목적에 따른 데이터 비교
→ 근거와 출처가 포함된 리포트 작성
→ 리포트 저장
→ 저장된 리포트 목록 조회·불러오기·삭제
```

역할 분담을 명확히 한다. **Server는 결정적인 데이터 작업만 수행한다** — OpenAlex 검색·상세조회, 비교용 지표 계산, SQLite 영속화. **비교의 해석과 리포트 산문은 LLM이 작성**해 Server에 넘겨 저장한다.

## Non-goals

- 논문 원문 PDF 수집 및 본문 파싱
- 인용·참고문헌 네트워크 탐색
- OpenAlex 외 데이터 소스 연동
- 다중 사용자 분리 및 접근 제어 (단일 사용자 로컬 stdio Server를 전제한다)
- Server가 리포트 산문이나 비교 해석 문장을 생성하는 것

## User flow

1. 사용자가 연구 질문을 제시한다.
2. LLM이 `search_papers`로 후보 논문을 탐색한다. 특정 논문을 제목으로 찾을 때는 `search_papers_by_title`을 쓴다.
3. 필요하면 `get_paper_details`로 초록·인용수·저널·오픈액세스 여부를 확인한다.
4. LLM이 선별한 논문을 `save_papers`로 저장한다.
5. `compare_papers`로 저장된 논문의 지표 표와 집계를 받는다.
6. LLM이 지표를 해석해 주장별 근거와 출처를 갖춘 리포트를 구성하고 `save_report`로 저장한다.
7. 이후 `list_reports`, `load_report`, `delete_report`로 리포트를 재활용하거나 정리한다.

## Functional requirements

- **FR1** OpenAlex 검색은 연구 주제 질의를 받고 발행 연도 범위, 최소 인용수, 오픈액세스 여부로 후보를 좁힐 수 있어야 한다. 정렬은 관련도·인용수·최신순 중에서 선택한다.
- **FR2** 단일 논문의 초록을 포함한 상세 정보를 조회할 수 있어야 한다.
- **FR3** 비교는 저장된 논문을 대상으로 하며, 논문별 지표 행과 전체 집계를 결정적으로 산출한다. Server는 해석 문장을 생성하지 않는다.
- **FR4** 리포트는 주장(claim)마다 출처 논문이 연결되어야 저장된다. 근거 없는 리포트는 저장할 수 없다.
- **FR5** 참고 논문과 리포트는 각각 저장·목록 조회·불러오기·삭제가 가능해야 한다.
- **FR6** 모든 데이터는 SQLite 파일에 보존되어 Server를 재시작해도 유지된다.
- **FR7** 리포트를 삭제해도 참고 논문은 보존되어 다른 리포트에서 계속 사용할 수 있다.

## Tool contracts

모든 Tool은 `@server.tool(structured_output=True)`로 등록하고 `dict[str, Any]`를 반환한다. 실패는 예외를 던지지 않고 `error` 키를 담은 dict로 반환한다 (기존 `server.py`의 규약).

### 검색·조회

| Tool | 입력 | 반환 |
|---|---|---|
| `search_papers_by_title` | `title: str`, `limit: int = 5` | `query`, `count`, `papers[]` |
| `search_papers` | `query: str`, `from_year: int \| None`, `to_year: int \| None`, `min_citations: int \| None`, `open_access_only: bool = False`, `sort: str = "relevance"`, `limit: int = 5` | `query`, `filters`, `sort`, `count`, `papers[]` |
| `get_paper_details` | `openalex_id: str` | `paper` (초록 포함) |

`sort`는 `relevance` / `citations` / `recency`만 허용한다. 기본값은 `relevance`다.

`papers[]` 항목의 필드: `openalex_id`, `title`, `publication_year`, `authors[]`, `doi`, `venue`, `cited_by_count`, `is_open_access`, `landing_page_url`. `get_paper_details`는 여기에 `abstract`를 더한다.

### 비교

| Tool | 입력 | 반환 |
|---|---|---|
| `compare_papers` | `openalex_ids: list[str]` | `rows[]`, `summary` |

`rows[]`: 논문별 `openalex_id`, `title`, `publication_year`, `cited_by_count`, `is_open_access`, `venue`, `author_count`.
`summary`: `paper_count`, `year_range`, `most_cited`, `least_cited`, `total_citations`, `open_access_count`.

저장되지 않은 `openalex_id`가 하나라도 있으면 저장하지 않고 `missing_ids`와 함께 거부한다.

### 논문 저장

| Tool | 입력 | 반환 |
|---|---|---|
| `save_papers` | `openalex_ids: list[str]` | `saved[]`, `failed[]`, `saved_count` |
| `list_saved_papers` | `limit: int = 20` | `count`, `papers[]` |
| `delete_saved_paper` | `openalex_id: str` | `deleted: bool` 또는 `error` + `referenced_by[]` |

`delete_saved_paper`는 해당 논문이 리포트 근거로 참조 중이면 삭제하지 않고 참조 중인 리포트 목록을 반환한다.

### 리포트

| Tool | 입력 | 반환 |
|---|---|---|
| `save_report` | `title: str`, `research_question: str`, `summary: str`, `findings: list[dict]` | `report_id`, `finding_count`, `paper_count` |
| `list_reports` | `limit: int = 20` | `count`, `reports[]` |
| `load_report` | `report_id: int` | `report`, `findings[]`, `papers[]` |
| `delete_report` | `report_id: int` | `deleted: bool`, `deleted_findings` |

`findings[]` 각 항목: `claim: str` (필수), `evidence: str` (선택), `paper_openalex_id: str` (필수).

## Persistence requirements

SQLite 파일 경로는 환경변수 `RESEARCH_DB_PATH`로 지정하며, 기본값은 저장소 루트의 `research.db`다. 스키마는 첫 연결 시 생성한다.

```sql
papers(openalex_id PK, title, publication_year, authors, doi, venue,
       cited_by_count, is_open_access, landing_page_url, abstract, saved_at)

reports(id PK, title, research_question, summary, created_at)

report_findings(id PK, report_id -> reports(id) ON DELETE CASCADE,
                position, claim, evidence, paper_openalex_id -> papers(openalex_id))
```

`report_findings`가 리포트↔논문 N:M 연결과 주장–출처 매핑을 동시에 표현한다. 리포트의 참고 논문 목록은 이 테이블에서 유도하며, 같은 사실을 저장하는 별도 연결 테이블은 두지 않는다.

제약 사항:

- `ON DELETE CASCADE`가 동작하려면 연결마다 `PRAGMA foreign_keys = ON`을 실행해야 한다.
- 동기 Tool 함수가 스레드 풀에서 실행될 수 있으므로 연결을 전역으로 공유하지 않고 호출마다 열고 닫는다.
- `save_report`의 리포트 삽입과 findings 삽입은 단일 트랜잭션으로 처리해 부분 저장을 방지한다.
- `papers`는 `openalex_id` 기준 upsert이며 재저장 시 최신 지표로 갱신된다.

## Error behavior

Tool은 예외를 밖으로 던지지 않는다. 아래 상황을 `error` 메시지로 구분해 반환한다.

| 상황 | 처리 |
|---|---|
| 검색어가 비어 있음 | `error`와 빈 `papers[]` |
| OpenAlex HTTP 오류 | 상태 코드를 담은 `error` |
| OpenAlex 요청 한도 초과(429) | 재시도해도 소용없으므로 `Retry-After` 기반 대기 시간을 담은 `error`. 키가 없으면 `OPENALEX_API_KEY` 설정을 함께 안내한다 |
| OpenAlex 연결 실패 | 사유를 담은 `error` |
| OpenAlex 응답 수신·해석 실패 | 본문을 읽는 도중의 타임아웃과 JSON이 아닌 본문도 `error`로 변환한다 |
| SQLite 접근 실패 | 경로 오설정·잠금 등으로 저장소가 실패하면 Tool 경계에서 잡아 `error`로 변환한다 |
| 허용되지 않은 `sort` 값 | 허용 값을 알려주는 `error` |
| `compare_papers`에 미저장 논문 ID | `error` + `missing_ids[]` |
| `save_report`의 `findings`가 비어 있음 | 근거가 필요하다는 `error` |
| `findings` 항목의 `claim`이 공백 | 해당 위치를 알려주는 `error` |
| `findings`가 미저장 논문을 참조 | `error` + `missing_ids[]` (먼저 `save_papers` 호출 유도) |
| 존재하지 않는 `report_id` | `error` |
| 참조 중인 논문 삭제 시도 | `error` + `referenced_by[]` |

## Completion criteria

1. `search_papers`가 연도·인용수·오픈액세스 필터와 세 가지 정렬을 적용해 결과를 반환한다.
2. `get_paper_details`가 초록을 복원해 반환한다.
3. `save_papers` → `compare_papers`가 지표 행과 집계를 반환한다.
4. `findings`가 비어 있거나 미저장 논문을 참조하는 `save_report`가 거부된다.
5. 정상 `save_report` 이후 `list_reports`·`load_report`가 근거와 출처를 포함해 리포트를 재현한다.
6. `delete_report` 후 리포트와 findings는 사라지고 `papers`는 남는다.
7. Server 재시작 후에도 저장된 데이터가 유지된다.
8. `server.py`가 stdio로 오류 없이 기동하고 Tool 목록이 노출된다.

## Constraints

- Python 3.10 이상.
- 의존성은 `mcp==2.0.0`만 사용한다. SQLite·HTTP·JSON은 표준 라이브러리(`sqlite3`, `urllib`, `json`)로 처리하며 `requirements.txt`에 추가하지 않는다.
- 전송 방식은 stdio를 유지한다.
- `OPENALEX_API_KEY`는 선택 사항이며, 없어도 검색이 동작해야 한다. 다만 무인증 한도가 낮아 실사용에서는 키 설정을 전제한다.
- 코드는 역할별로 분리한다. `server.py`는 Tool 정의와 입출력 계약, `openalex.py`는 외부 통신, `storage.py`는 영속화를 담당한다.

## Assumptions

- OpenAlex 공개 API는 인증 없이도 호출되지만 한도가 낮다. 실측한 무인증 한도는 하루 1,000 크레딧이고 검색 1회가 10 크레딧을 소비해, 한 세션의 탐색만으로도 소진되어 `429`와 약 22시간의 대기가 발생했다. `OPENALEX_API_KEY`를 설정하면 10,000 크레딧으로 올라간다. 따라서 실사용은 키가 있는 상태를 전제한다.
- 아래 쿼리 문법은 실제 요청으로 확인했다: `filter=publication_year:2020-2024,cited_by_count:>50,open_access.is_oa:true`, `sort=cited_by_count:desc`, `select`에 `abstract_inverted_index` 포함.
- 단일 사용자가 로컬에서 하나의 Server 프로세스를 사용한다.
- 리포트 본문의 품질(주장이 근거에 실제로 부합하는지)은 LLM의 책임이며 Server는 구조적 요건만 강제한다.

## Open risks

- **인용수 정렬과 주제 적합성의 충돌**: `search` 질의에 `sort=cited_by_count:desc`를 함께 적용하면 인용수만 높고 주제와 무관한 논문이 상위에 오는 것을 확인했다. 기본 정렬을 관련도로 두고, 인용수 정렬은 필터로 후보군을 좁힌 뒤 쓰도록 Tool 설명에 명시한다.
- **초록 부재**: OpenAlex에 `abstract_inverted_index`가 없는 레코드가 존재한다. 이 경우 `abstract`는 `null`이며 LLM이 초록 없이 판단해야 한다.
- **저장 시점 지표의 고정**: `papers`에 저장된 인용수는 저장 시점 값이다. 시간이 지나면 실제 값과 벌어지며, 갱신하려면 `save_papers`를 다시 호출해야 한다.
- **OpenAlex 응답 필드 누락**: `primary_location`이나 `authorships`가 비어 있는 레코드가 있어 `venue`, `authors`가 빈 값일 수 있다.
