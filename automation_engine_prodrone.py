#!/usr/bin/env python3
"""로컬 실행용 래퍼(선택)

GitHub Actions 없이 로컬에서 수동 실행할 때 사용합니다.
환경변수(WP_USER, WP_APP_PASSWORD, GEMINI_API_KEY)는 쉘에서 export 하거나,
같은 폴더의 .env 파일에 KEY=VALUE 형태로 넣어두면 자동 로드합니다.

예)
  TARGET_URL="https://drone.jp/news/20260227113208126295.html" \
  POST_STATUS=draft FORCE_UPDATE=false \
  python automation_engine_prodrone.py
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "translate_and_post_prodrone.py"
ENV_FILE = HERE / ".env"

def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def main() -> int:
    load_dotenv(ENV_FILE)

    if not SCRIPT.exists():
        raise SystemExit(f"❌ 스크립트 없음: {SCRIPT}")

    missing = [k for k in ("WP_USER", "WP_APP_PASSWORD", "GEMINI_API_KEY") if not os.environ.get(k)]
    if missing:
        print("⚠️  누락된 환경변수:", ", ".join(missing))
        print("   - 로컬은 export 하거나 .env 파일을 만들어 주세요.")

    cmd = ["python", str(SCRIPT)]
    print("[*] 실행:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(HERE))
    return proc.returncode

if __name__ == "__main__":
    raise SystemExit(main())
