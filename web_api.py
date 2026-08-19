"""저장된 리포트를 웹 UI가 읽을 수 있도록 HTTP로 노출한다.

읽기 전용 조회만 제공한다. 논문·리포트의 저장과 삭제는 MCP Tool의 책임으로
남기고, 이 모듈은 storage가 돌려준 값을 JSON으로 직렬화하는 일만 한다.

MCP Server의 stdio 전송과는 별개의 프로세스다. 브라우저는 stdio로 말할 수
없으므로 같은 SQLite 파일을 읽는 HTTP 창구를 따로 둔다.

실행:
    .venv\\Scripts\\python.exe web_api.py
"""

from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import storage


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# storage.list_reports가 LIMIT을 요구한다. 단일 사용자의 로컬 리포트 수를
# 넉넉히 덮는 값으로 두고 페이지네이션은 두지 않는다.
REPORT_LIST_LIMIT = 200

# 자릿수를 묶어 SQLite가 다루는 정수 범위를 넘지 않게 한다. 범위를 넘는 값을
# 그대로 넘기면 sqlite3가 OverflowError를 던지는데, 이는 sqlite3.Error가 아니라
# 저장소 오류 처리에 걸리지 않고 핸들러를 죽인다.
_REPORT_DETAIL_PATH = re.compile(r"^/api/reports/(\d{1,18})$")


class ReportRequestHandler(BaseHTTPRequestHandler):
    """리포트 목록과 상세, 두 경로만 처리한다."""

    server_version = "ResearchReportAPI/1.0"

    def do_GET(self) -> None:
        # 질의 문자열이 붙어도 경로 판정이 흔들리지 않게 경로만 떼어 쓴다.
        path = urlsplit(self.path).path
        detail = _REPORT_DETAIL_PATH.match(path)

        try:
            if path == "/api/reports":
                reports = storage.list_reports(REPORT_LIST_LIMIT)
                self._send_json(200, {"count": len(reports), "reports": reports})
            elif detail is not None:
                self._send_report(int(detail.group(1)))
            else:
                self._send_json(404, {"error": f"{path} 경로는 없습니다."})
        except storage.DatabaseError as error:
            self._send_json(500, {"error": f"리포트를 읽지 못했습니다: {error}"})

    def _send_report(self, report_id: int) -> None:
        report = storage.get_report(report_id)
        if report is None:
            self._send_json(404, {"error": f"{report_id}번 리포트를 찾지 못했습니다."})
            return
        self._send_json(200, report)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve() -> None:
    """API 서버를 띄운다. 주소와 포트는 환경변수로 바꿀 수 있다."""

    host = os.getenv("WEB_API_HOST", DEFAULT_HOST)
    port = int(os.getenv("WEB_API_PORT", str(DEFAULT_PORT)))

    # 접근 제어가 없으므로 루프백에만 붙인다. SPEC의 단일 사용자 로컬 전제와 같다.
    server = ThreadingHTTPServer((host, port), ReportRequestHandler)
    print(f"리포트 API: http://{host}:{port}/api/reports")
    print(f"SQLite: {storage.database_path()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
