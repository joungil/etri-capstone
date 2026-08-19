# OpenAlex 기반 연구 지원 MCP Server

## 실습 목표

MCP Server를 직접 구현하여 LLM이 논문을 찾고 분석·비교하며, 작성한 리포트를 저장하고 다시 활용할 수 있게 한다.

## 요구사항

- OpenAlex를 활용한 논문 검색
- LLM이 식별하고 호출할 수 있는 MCP Tool 제공
- 연구 분야에 맞는 논문 분석 및 비교
- 근거와 출처가 포함된 리포트 작성
- 참고 논문과 리포트 저장, 목록 조회, 불러오기 및 삭제
- SQLite를 사용한 데이터 보존

완성된 결과물은 다음 흐름을 지원해야 한다.

```text
연구 질문
→ OpenAlex를 활용한 논문 검색
→ 연구 목적에 따른 데이터 비교
→ 근거와 출처가 포함된 리포트 작성
→ 리포트 저장
→ 저장된 리포트 목록 조회·불러오기·삭제
```

## 구현

Server는 결정적인 데이터 작업만 담당한다. OpenAlex 검색과 상세 조회, 비교용 지표 계산, SQLite 보존까지가 Server의 몫이고, 비교 결과의 해석과 리포트 산문은 LLM이 작성해 Server에 넘겨 저장한다.

역할별로 파일을 나눴다.

```text
server.py        Tool 정의와 입출력 검증
openalex.py      OpenAlex API 통신과 응답 정규화
storage.py       SQLite 스키마와 논문·리포트 보존
report_export.py 리포트의 마크다운 렌더링과 파일 쓰기
verify_flow.py   전체 흐름을 한 번 실행해 보는 수동 검증 스크립트
```

상세한 요구사항과 계약은 `SPEC.md`에 정리되어 있다.

## 준비

Python 3.10 이상이 필요하다.

먼저 Python 버전을 확인한다. 3.10보다 낮다면 설치된 Python 3.10 이상의 실행 명령을 사용한다.

```bash
python3 --version
```

Windows PowerShell:

```powershell
python --version
```

macOS와 Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## MCP Server 실행

```bash
python server.py
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe server.py
```

MCP Host는 위 명령으로 Server를 실행하고 표준 입력과 표준 출력을 통해 통신한다.

## MCP Host 연결

저장소 루트에 `.mcp.json`을 만들면 Host가 이 Server를 붙인다. 경로는 각자의 환경에 맞춰야 하므로 이 파일은 저장소에 포함하지 않는다.

```json
{
  "mcpServers": {
    "openalex-research": {
      "command": "/절대경로/etri-capstone/.venv/bin/python",
      "args": ["/절대경로/etri-capstone/server.py"],
      "env": {
        "OPENALEX_API_KEY": "<발급받은 키>"
      }
    }
  }
}
```

Windows에서는 경로 구분자를 `\\`로 쓰고 인터프리터는 `.venv\\Scripts\\python.exe`를 가리킨다.

`env.OPENALEX_API_KEY`는 형식상 선택 사항이지만 실질적으로는 넣는 편이 좋다. 키 없이 호출하면 하루 1,000 크레딧(검색 1회당 10 크레딧)을 공유하는 무인증 한도가 적용되어, 조금만 검색해도 `HTTP 429`가 나고 리셋까지 하루 가까이 기다려야 한다. 키를 넣으면 한도가 10,000 크레딧으로 올라간다.

키는 저장소에 커밋하지 않는다. `.mcp.json`은 `.gitignore`에 등록되어 있어 위 내용을 그대로 채워도 추적되지 않지만, 문서나 이슈에 붙여넣을 때는 값을 가린다. 키를 파일에 두고 싶지 않으면 `env` 항목을 빼고 셸 환경변수 `OPENALEX_API_KEY`로 지정해도 된다.

파일을 만든 뒤 Host를 재시작하고, 연결 상태와 Tool 목록이 노출되는지 확인한다. 이미 붙어 있는 Server 프로세스는 기동 시점의 환경변수를 그대로 쓰므로, `env`를 바꿨다면 Host를 다시 시작해야 반영된다.

## 제공 Tool

### 검색과 조회

| Tool | 설명 |
|---|---|
| `search_papers_by_title` | 제목을 알고 있는 특정 논문을 찾는다 |
| `search_papers` | 연구 주제로 후보군을 탐색한다. 발행 연도·최소 인용수·오픈액세스 필터와 관련도/인용수/최신순 정렬을 지원한다 |
| `search_papers_by_meaning` | 질의의 의미로 후보군을 탐색한다. 같은 단어를 쓰지 않은 논문도 찾는다 |
| `get_paper_details` | 논문 한 편의 초록·인용수·저널·오픈액세스 여부를 조회한다 |

검색 Tool이 둘인 이유는 OpenAlex가 성격이 다른 두 검색을 제공하기 때문이다. `search_papers`는 단어가 일치하는 논문을, `search_papers_by_meaning`은 의미가 가까운 논문을 찾는다. 후자는 OpenAlex 베타 기능이라 최소 인용수 필터와 정렬을 지원하지 않고, 후보가 유사도 상위 50건으로 제한되며, 호출이 초당 1회로 묶인다. 그래서 하나로 합치지 않고 나눠 두었다. 자세한 차이는 `SPEC.md`의 Tool contracts에 있다.

### 비교

| Tool | 설명 |
|---|---|
| `compare_papers` | 저장된 논문의 지표를 한 표로 모으고 연도 범위·인용수·오픈액세스 비율을 집계한다. 해석 문장은 만들지 않는다 |

### 참고 논문

| Tool | 설명 |
|---|---|
| `save_papers` | 참고 논문을 초록까지 함께 저장한다. 이미 저장된 논문은 최신 정보로 갱신한다 |
| `list_saved_papers` | 저장된 참고 논문 목록을 조회한다 |
| `delete_saved_paper` | 참고 논문을 삭제한다. 리포트가 근거로 쓰고 있으면 거부한다 |

### 리포트

| Tool | 설명 |
|---|---|
| `save_report` | 주장마다 출처 논문을 연결한 리포트를 저장한다. 근거가 없거나 저장되지 않은 논문을 가리키면 거부한다 |
| `list_reports` | 저장된 리포트 목록을 조회한다 |
| `load_report` | 리포트를 본문·근거·참고 논문과 함께 불러온다 |
| `export_report` | 리포트를 마크다운 파일로 내보낸다. 같은 리포트는 항상 같은 파일에 덮어쓴다 |
| `delete_report` | 리포트를 삭제한다. 참고 논문은 남긴다 |

### 리포트 내보내기

`export_report`는 리포트를 `reports/report-<id>.md`에 쓴다. 파일 이름이 리포트 ID로 고정되므로 같은 리포트를 다시 내보내면 이전 파일을 덮어쓰고, 한 파일에 여러 리포트가 누적되지 않는다. 이 폴더는 SQLite에 있는 내용의 읽기용 사본이라 `.gitignore`에 등록해 두었다.

## 환경 변수

| 변수 | 설명 |
|---|---|
| `OPENALEX_API_KEY` | 선택 사항. 없어도 검색은 동작하지만 무인증 한도(하루 1,000 크레딧)에 걸려 `HTTP 429`가 나기 쉽다. 키를 넣으면 10,000 크레딧으로 올라간다 |
| `RESEARCH_DB_PATH` | 선택 사항. SQLite 파일 경로. 기본값은 저장소의 `research.db` |
| `REPORT_EXPORT_DIR` | 선택 사항. `export_report`가 마크다운을 저장할 폴더. 기본값은 저장소의 `reports` |

## 동작 검증

Tool을 순서대로 호출해 검색부터 삭제까지 전체 흐름을 확인한다. 임시 DB를 사용하므로 `research.db`는 건드리지 않는다.

```bash
python verify_flow.py
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe verify_flow.py
```

종료 코드로 결과를 구분한다.

| 코드 | 의미 |
|---|---|
| 0 | 모든 단계 통과 |
| 1 | 실패한 단계가 있음 |
| 2 | 실행한 단계는 통과했으나 OpenAlex 호출 실패로 일부 단계가 미검증 |

의미 검색(2단계)은 OpenAlex 베타 기능이라 간헐적으로 실패한다. 이 단계만 실패하면 나머지는 그대로 진행하고 미검증으로 남겨 종료 코드 2를 돌려준다.

## 프로젝트 스킬

저장소를 내려받아 프로젝트 루트에서 LLM 애플리케이션을 실행하면 `.claude/skills`의 스킬을 사용할 수 있다.

```text
/interview 구현할 기능의 요구사항을 명세로 정리
/code-review 현재 변경에서 수정이 필요한 문제만 검토
```
