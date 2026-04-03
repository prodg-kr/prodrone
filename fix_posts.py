#!/usr/bin/env python3
"""
기존 게시글 MD 파일 일괄 문구 치환 스크립트
실행 위치: Hugo 레포 루트 (content/posts/ 폴더가 있는 곳)

변경 내용:
1. 원문 링크 제거
2. "원문을 참고해 요약·정리한 내용" → "proDRONE.kr 편집팀이 취재·분석하여 작성한 콘텐츠"
3. "저작권 관련 문의는 [Contact](/contact/)로 연락주세요." 제거
"""

import re
from pathlib import Path

POSTS_DIR = Path("content/posts")
DRY_RUN = False  # True로 설정하면 실제 변경 없이 미리보기만

def fix_md_file(path: Path) -> bool:
    text = path.read_text(encoding='utf-8')
    original = text

    # 1) **원문:** [...](url) 줄 제거
    text = re.sub(r'\*\*원문:\*\* \[.*?\]\(https?://[^\)]+\)\n\n?', '', text)

    # 2) 저작권 문구 → 자체 제작 문구로 교체
    text = re.sub(
        r'> 본 글은 원문을 참고해 한국 독자를 위해 요약·정리한 내용입니다\..*?연락주세요\.',
        '> 본 기사는 **proDRONE.kr** 편집팀이 해외 드론 산업 동향을 취재·분석하여 한국 독자를 위해 작성한 콘텐츠입니다.',
        text,
        flags=re.DOTALL
    )

    # 3) 혹시 남아있는 변형 문구도 처리
    text = re.sub(
        r'> 본 글은 원문을 참고해.*?연락주세요\.',
        '> 본 기사는 **proDRONE.kr** 편집팀이 해외 드론 산업 동향을 취재·분석하여 한국 독자를 위해 작성한 콘텐츠입니다.',
        text,
        flags=re.DOTALL
    )

    if text == original:
        return False  # 변경 없음

    if not DRY_RUN:
        path.write_text(text, encoding='utf-8')
    return True


def main():
    if not POSTS_DIR.exists():
        print(f"❌ {POSTS_DIR} 폴더를 찾을 수 없습니다. Hugo 레포 루트에서 실행하세요.")
        return

    files = list(POSTS_DIR.glob("*.md"))
    print(f"📂 총 {len(files)}개 MD 파일 검사 중...")
    print(f"{'[DRY RUN]' if DRY_RUN else '[실제 변경]'}\n")

    changed = 0
    skipped = 0

    for f in sorted(files):
        if fix_md_file(f):
            print(f"  ✅ 변경: {f.name}")
            changed += 1
        else:
            skipped += 1

    print(f"\n{'='*50}")
    print(f"완료: {changed}개 변경 / {skipped}개 변경 없음")
    if DRY_RUN:
        print("※ DRY_RUN=True 상태입니다. 실제 변경하려면 DRY_RUN=False로 변경 후 재실행하세요.")


if __name__ == "__main__":
    main()
