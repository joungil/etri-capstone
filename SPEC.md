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
2. LLM이 `search_papers`로 후보 논문을 탐색한다. 어떤 용어로 불리는 주제인지 모를 때는 `search_papers_by_meaning`으로 의미가 가까운 논문을 함께 찾는다. 특정 논문을 제목으로 찾을 때는 `search_papers_by_title`을 쓴다.
3. 필요하면 `get_paper_details`로 초록·인용수·저널·오픈액세스 여부를 확인한다.
4. LLM이 선별한 논문을 `save_papers`로 저장한다.
5. `compare_papers`로 저장된 논문의 지표 표와 집계를 받는다.
6. LLM이 지표를 해석해 주장별 근거와 출처를 갖춘 리포트를 구성하고 `save_report`로 저장한다.
7. 이후 `list_reports`, `load_report`, `delete_report`로 리포트를 재활용하거나 정리한다.
8. 저장한 리포트를 사람이 읽을 때는 웹 뷰어를 쓴다.

## Functional requirements

- **FR1** OpenAlex 검색은 연구 주제 질의를 받고 발행 연도 범위, 최소 인용수, 오픈액세스 여부로 후보를 좁힐 수 있어야 한다. 정렬은 관련도·인용수·최신순 중에서 선택한다.
- **FR1a** 질의와 같은 단어를 쓰지 않은 논문도 찾을 수 있도록, 의미 기반 검색을 별도 Tool로 제공한다. 어휘 검색과 계약이 다르므로(정렬·최소 인용수 미지원, 후보군 상한) 같은 Tool에 모드로 합치지 않는다.
- **FR2** 단일 논문의 초록을 포함한 상세 정보를 조회할 수 있어야 한다.
- **FR3** 비교는 저장된 논문을 대상으로 하며, 논문별 지표 행과 전체 집계를 결정적으로 산출한다. Server는 해석 문장을 생성하지 않는다.
- **FR4** 리포트는 주장(claim)마다 출처 논문이 연결되어야 저장된다. 근거 없는 리포트는 저장할 수 없다.
- **FR5** 참고 논문과 리포트는 각각 저장·목록 조회·불러오기·삭제가 가능해야 한다.
- **FR6** 모든 데이터는 SQLite 파일에 보존되어 Server를 재시작해도 유지된다.
- **FR7** 리포트를 삭제해도 참고 논문은 보존되어 다른 리포트에서 계속 사용할 수 있다.
- **FR8** 저장된 리포트를 사람이 읽는 통로는 웹 뷰어 하나로 둔다. 파일로 내보내는 Tool은 제공하지 않는다. 읽는 곳이 하나면 본문 형식을 그 화면에 맞춰 정할 수 있고, 텍스트 파일용 이스케이프 규칙을 따로 유지할 필요도 없다.

## Tool contracts

모든 Tool은 `@server.tool(structured_output=True)`로 등록하고 `dict[str, Any]`를 반환한다. 실패는 예외를 던지지 않고 `error` 키를 담은 dict로 반환한다 (기존 `server.py`의 규약).

### 검색·조회

| Tool | 입력 | 반환 |
|---|---|---|
| `search_papers_by_title` | `title: str`, `limit: int = 5` | `query`, `count`, `papers[]` |
| `search_papers` | `query: str`, `from_year: int \| None`, `to_year: int \| None`, `min_citations: int \| None`, `open_access_only: bool = False`, `sort: str = "relevance"`, `limit: int = 5` | `query`, `filters`, `sort`, `count`, `papers[]` |
| `search_papers_by_meaning` | `query: str`, `from_year: int \| None`, `to_year: int \| None`, `open_access_only: bool = False`, `limit: int = 5` | `query`, `filters`, `count`, `papers[]` |
| `get_paper_details` | `openalex_id: str` | `paper` (초록 포함) |

`sort`는 `relevance` / `citations` / `recency`만 허용한다. 기본값은 `relevance`다.

`search_papers`는 OpenAlex `search` 파라미터를, `search_papers_by_meaning`은 `search.semantic` 파라미터를 사용한다. 두 Tool의 계약 차이는 OpenAlex가 의미 검색에 거는 제약에서 온다.

| 항목 | `search_papers` | `search_papers_by_meaning` |
|---|---|---|
| 매칭 방식 | 제목·초록·전문의 단어 일치 | 임베딩 유사도 |
| `min_citations` | 지원 | **미지원** (OpenAlex가 `cited_by_count` 필터를 거부한다) |
| `sort` | 지원 | **미지원** (값을 넘겨도 무시되므로 파라미터로 받지 않는다) |
| 후보군 | 조건에 맞는 전체 | 유사도 상위 50건. `limit`을 키워도 그 이상 나오지 않는다 |
| 호출 빈도 | 제한 없음 | **초당 1회** |
| 안정성 | 안정 | OpenAlex 베타. 간헐적 `504` 발생 |

의미 검색이 받아들이는 필터는 `publication_year`, `open_access.is_oa`, `is_oa`, `type`, `language`, `has_abstract`, `has_fulltext`, `is_retracted`, `author.id`, `authorships.author.id`, `authorships.institutions.id`, `institution.id`, `institutions.id`, `funders.id`, `primary_location.license`, `primary_location.source.id`다. 이 Tool은 이 중 발행 연도와 오픈액세스 여부만 노출한다.

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

SQLite 파일이 리포트의 유일한 원본이다. 사본을 파일로 따로 두지 않으므로 `delete_report`는 그 리포트를 되돌릴 수 없게 지운다.

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
| OpenAlex 요청 한도 초과(429) | `Retry-After` 기반 대기 시간을 담은 `error`. 대기가 1분 이상이면 크레딧 소진이므로 키가 없을 때 `OPENALEX_API_KEY` 설정을 함께 안내한다. 대기가 1분 미만이면 의미 검색의 초당 1회 제한이며, 키와 무관하므로 안내를 덧붙이지 않고 초 단위로 알린다 |
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
2. `search_papers_by_meaning`이 질의 단어를 포함하지 않는 논문을 결과에 포함하고, 연도·오픈액세스 필터를 적용한다.
3. `get_paper_details`가 초록을 복원해 반환한다.
4. `save_papers` → `compare_papers`가 지표 행과 집계를 반환한다.
5. `findings`가 비어 있거나 미저장 논문을 참조하는 `save_report`가 거부된다.
6. 정상 `save_report` 이후 `list_reports`·`load_report`가 근거와 출처를 포함해 리포트를 재현한다.
7. `delete_report` 후 리포트와 findings는 사라지고 `papers`는 남는다.
8. Server 재시작 후에도 저장된 데이터가 유지된다.
9. `server.py`가 stdio로 오류 없이 기동하고 Tool 목록이 노출된다.
10. 웹 뷰어의 목록에서 리포트를 눌러 상세 페이지로 이동하면 본문·근거·출처·참고 논문을 읽을 수 있다.

## 웹 리포트 뷰어

저장된 리포트를 브라우저에서 목록으로 보고 상세 페이지에서 읽기 위한 부속 구성이다. MCP Tool 표면에는 포함되지 않는다.

- **WV1** 리포트 목록과 리포트 상세를 각각 별도 주소로 볼 수 있어야 한다. 목록에서 항목을 누르면 그 리포트의 상세 주소로 이동한다.
- **WV2** 상세 페이지는 본문, 주장별 근거, 주장이 가리키는 출처 논문, 참고 논문 목록을 보여준다. 저장된 리포트를 사람이 읽는 것이 목적이므로 초록도 함께 노출한다.
- **WV3** 뷰어는 읽기 전용이다. 저장·삭제·수정은 MCP Tool의 책임으로 남긴다.
- **WV4** 리포트가 없거나 API에 연결하지 못한 상태를 화면에서 구분해 알린다. 둘 다 빈 목록으로 보이면 원인을 알 수 없다.
- **WV5** 참고 논문의 지표는 HTML `<table>`로 표시한다. 나란히 놓고 비교하는 값이므로 문자로 그린 표나 나열식 목록보다 표가 맞다. 표가 화면보다 넓어지면 표만 가로로 스크롤하고 페이지 본문은 밀리지 않는다.
- **WV6** 리포트 본문은 빈 줄을 문단 경계로 보아 문단마다 나누어 표시한다. 한 덩어리로 그리면 문단 경계가 빈 줄로만 보여 글의 구조가 드러나지 않는다. 문단 안의 줄바꿈은 그대로 살린다.

브라우저는 stdio로 말할 수 없으므로 같은 SQLite 파일을 읽는 HTTP 창구를 별도 프로세스로 둔다. `web_api.py`가 `GET /api/reports`와 `GET /api/reports/<id>` 두 경로만 제공하며, 응답 형태는 각각 `list_reports`, `load_report`와 같다. 같은 데이터 형태를 두 번 정의하지 않기 위해 `storage`의 반환값을 그대로 직렬화한다.

화면은 `web/`의 React 앱이 그린다. 개발 서버는 `localhost:3000`에 고정하고, `/api` 요청만 `web_api.py`로 프록시해 브라우저에서 같은 출처로 보이게 한다. 그래서 API에 CORS 헤더를 두지 않는다.

이 화면의 시각 결정(색 토큰, 타입 스케일, 폰트 선택, 다크 모드, 접근성 기준)은 `DESIGN.md`에 따로 정리했다.

## Constraints

- Python 3.10 이상.
- Server의 의존성은 `mcp==2.0.0`만 사용한다. SQLite·HTTP·JSON은 표준 라이브러리(`sqlite3`, `urllib`, `json`)로 처리하며 `requirements.txt`에 추가하지 않는다. `web_api.py`도 이 제약을 따라 `http.server`로 구현한다.
- MCP Server의 전송 방식은 stdio를 유지한다. 웹 뷰어의 HTTP는 MCP 전송이 아니라 브라우저용 조회 창구이며, 별도 프로세스로 분리해 이 제약을 벗어나지 않는다.
- 웹 뷰어의 프론트엔드 의존성은 `web/package.json`에만 둔다. React와 라우터, 빌드 도구로 한정하고 UI 프레임워크는 도입하지 않는다.
- `web_api.py`는 루프백에만 바인딩한다. 접근 제어가 없으므로 단일 사용자 로컬 전제를 벗어나지 않는다.
- `OPENALEX_API_KEY`는 선택 사항이며, 없어도 검색이 동작해야 한다. 다만 무인증 한도가 낮아 실사용에서는 키 설정을 전제한다.
- 코드는 역할별로 분리한다. `server.py`는 Tool 정의와 입출력 계약, `openalex.py`는 외부 통신, `storage.py`는 영속화, `web_api.py`는 리포트 조회의 HTTP 직렬화를 담당한다.

## Assumptions

- OpenAlex 공개 API는 인증 없이도 호출되지만 한도가 낮다. 실측한 무인증 한도는 하루 1,000 크레딧이고 검색 1회가 10 크레딧을 소비해, 한 세션의 탐색만으로도 소진되어 `429`와 약 22시간의 대기가 발생했다. `OPENALEX_API_KEY`를 설정하면 10,000 크레딧으로 올라간다. 따라서 실사용은 키가 있는 상태를 전제한다.
- 아래 쿼리 문법은 실제 요청으로 확인했다: `filter=publication_year:2020-2024,cited_by_count:>50,open_access.is_oa:true`, `sort=cited_by_count:desc`, `select`에 `abstract_inverted_index` 포함.
- 의미 검색의 제약도 실제 요청으로 확인했다. `search.semantic`은 `meta.count`가 항상 50으로 고정되고, `per_page`가 50을 넘으면 `400`, `cited_by_count` 필터도 `400`이다. `sort`는 존재하지 않는 값을 넘겨도 오류 없이 무시된다. 초당 2회 이상 호출하면 `429`에 `Retry-After: 1`이 실려 온다. 유효한 검색 파라미터 전체는 `search`, `search.semantic`, `search.exact`, `search.title`, `search.title.exact`, `search.title_and_abstract`, `search.title_and_abstract.exact`이며, 이는 잘못된 파라미터를 보냈을 때 OpenAlex가 반환한 목록이다.
- 단일 사용자가 로컬에서 하나의 Server 프로세스를 사용한다.
- 리포트 본문의 품질(주장이 근거에 실제로 부합하는지)은 LLM의 책임이며 Server는 구조적 요건만 강제한다.

## Open risks

- **인용수 정렬과 주제 적합성의 충돌**: `search` 질의에 `sort=cited_by_count:desc`를 함께 적용하면 인용수만 높고 주제와 무관한 논문이 상위에 오는 것을 확인했다. 기본 정렬을 관련도로 두고, 인용수 정렬은 필터로 후보군을 좁힌 뒤 쓰도록 Tool 설명에 명시한다.
- **초록 부재**: OpenAlex에 `abstract_inverted_index`가 없는 레코드가 존재한다. 이 경우 `abstract`는 `null`이며 LLM이 초록 없이 판단해야 한다. 더 앞선 문제는 검색 재현율이다. `search`는 제목·초록·전문을 훑으므로 초록이 없는 레코드는 색인 대상이 제목뿐이고, 제목에 없는 전문 용어로 질의하면 후보에 아예 오르지 않는다. EUROCRYPT 2026의 `Deep Neural Cryptography`가 실제로 그랬다. `cryptanalysis`, `distinguisher` 같은 용어로는 어떤 연도 조건에서도 잡히지 않았고, 제목 단어를 쓰고 연도를 2026으로 좁히자 2위로 올라왔다. 연도를 좁힌 짧고 일반적인 질의를 함께 쓰도록 Tool 설명에 명시한다.
- **의미 검색의 베타 상태**: OpenAlex는 `search.semantic`을 베타로 표기하고 민감한 프로덕션 워크플로에 쓰지 말라고 안내한다. 실제로 연도 필터를 건 요청 하나가 `504 query_timeout`으로 실패했다가 재시도에서 성공했다. 계약과 파라미터가 예고 없이 바뀔 수 있으므로 어휘 검색을 대체하지 않고 별도 Tool로 병행한다.
- **의미 검색의 후보군 상한**: `search.semantic`은 유사도 상위 50건만 후보로 만든다. 넓은 주제에서는 관련 논문이 50건을 넘어도 그 이상 볼 수 없고, 연도·오픈액세스 필터는 이 50건을 만든 뒤가 아니라 만드는 과정에 적용되는지 확인하지 않았다. 재현율이 중요하면 질의를 바꿔 여러 번 호출하거나 `search_papers`를 함께 쓴다.
- **저장 시점 지표의 고정**: `papers`에 저장된 인용수는 저장 시점 값이다. 시간이 지나면 실제 값과 벌어지며, 갱신하려면 `save_papers`를 다시 호출해야 한다.
- **OpenAlex 응답 필드 누락**: `primary_location`이나 `authorships`가 비어 있는 레코드가 있어 `venue`, `authors`가 빈 값일 수 있다.
