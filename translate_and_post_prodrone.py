#!/usr/bin/env python3
"""
DRONE.jp 자동 번역 시스템 v9.4.0
파이프라인: 일본어 원문 → Gemini 번역 → Gemini 편집 → Hugo Markdown → GitHub Push

================================================================
v9.4.0 부분 수정 변경 요약 (2026-11-21, 감사 보고서 action-code-audit-2026-11-21.md 기반)
전면 재작성이 아니라 감사 지적만 수정했다. 그 외 동작은 v9.3.0과 동일하다.
----------------------------------------------------------------
[수정된 감사 지적]
- §3-2  슬러그 충돌 시 기존 MD 파일 무단 덮어쓰기 금지: 쓰기 전 파일 존재 검사.
         같은 원문 URL 재처리는 덮어쓰기 허용, 다른 글이면 -2/-3 suffix 부여.
         판정용으로 front matter에 source_url을 신규 기록한다.
- §3-4  중복 방지 2단계 추가: 1단계 posted JSON + 2단계 MD front matter의
         source_url 대조. posted JSON 손상 시 빈 리스트 반환 금지 → 에러 + exit 1.
         (2단계는 v9.4.0 이후 발행 글부터 유효 — 기존 파일엔 source_url이 없다.)
- §3-3  0건 출력 런은 exit 1로 실패 처리 (처리 대상이 있었는데 성공 0건).
         단, 수집 소스가 정상인데 신규 기사가 없는 날(토요일 등)은 정상 종료.
- §3-5  동시 실행 방지: 워크플로우 concurrency guard (auto-translate_prodrone.yml 참조).
- §3-14 front matter 제목·요약·cover alt의 개행 제거 (YAML 파손 방지).
[연관 수정]
- §3-9  Hugo 레포 클론/풀 실패 시 경고만 하고 계속하지 않고 exit 1 (빠른 실패).
- 버전 표기 단일화: v9.4.0 (헤더·실행 배너 동일). 배너 문구도 실제 동작에 맞게 수정.
- 데드 코드 제거: commit_posted_articles (호출 0회 — 실제 커밋은 워크플로우 담당).
[미수정 — 별도 결정 필요]
- §3-8  최근 글 내부링크 mtime 정렬, §3-12 RSS entry.link try 밖,
  §3-13 본문 정제 content_div 가드는 이번 범위에 포함되지 않았다.
  REWRITE_NOTES.md 참조.
================================================================
"""

import os
import sys
import requests
import feedparser
from datetime import datetime
from pathlib import Path
import json
import time
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup, NavigableString
import hashlib
import re
import subprocess
import base64

# ==========================================
# 설정
# ==========================================
GEMINI_API_KEY         = os.environ.get("GEMINI_API_KEY")
PRONEWS_RSS            = "https://drone.jp/feed"
PRONEWS_ARCHIVE_BASE   = "https://drone.jp/news/page"
PRONEWS_BASE_URL       = "https://drone.jp"
POSTED_ARTICLES_FILE   = "posted_articles_drone.json"
FORCE_UPDATE           = os.environ.get("FORCE_UPDATE", "false").lower() == "true"
DAILY_LIMIT            = 10
ARCHIVE_MAX_PAGES      = 20

# Hugo 사이트 레포 설정
HUGO_SITE_REPO         = os.environ.get("HUGO_SITE_REPO", "prodgkr/prodrone")
# Step 3 (owner chose option B): isolated preview-branch test.
# The branch to clone and push Hugo posts to. "main" = live behaviour.
HUGO_TARGET_BRANCH     = os.environ.get("HUGO_TARGET_BRANCH", "main").strip() or "main"
GITHUB_TOKEN           = os.environ.get("GITHUB_TOKEN")
HUGO_REPO_LOCAL        = Path("/tmp/prodrone-site")

# 실행 모드 감지
# RUN_MODE_OVERRIDE: 워크플로우 입력(event_name_override)으로 스케줄 경로를
# 브랜치에서 시험할 때 사용. GitHub Actions는 기본 GITHUB_* 환경 변수의
# 덮어쓰기를 무시하므로 GITHUB_EVENT_NAME을 직접 바꾸는 방식은 동작하지 않는다.
# (재검수 1번) 비어 있으면 실제 이벤트명(schedule/workflow_dispatch)을 쓴다.
EFFECTIVE_EVENT = os.environ.get("RUN_MODE_OVERRIDE", "").strip() or os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")
IS_SCHEDULED = EFFECTIVE_EVENT == "schedule"

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

# 단일 URL 1개만 처리할 때 사용 (예: https://drone.jp/news/...)
TARGET_URL  = os.environ.get("TARGET_URL", "").strip()

# 배포 검증(C1) — 이번 런에 새로 발행한 글의 라이브 URL 확인
PRODRONE_SITE_URL = "https://prodrone.kr"
# Step 3 (option B): verify against this base URL instead of the hard-coded
# production site, so a preview-branch deployment can be verified.
# Default is PRODRONE_SITE_URL — identical behaviour when unset.
DEPLOY_VERIFY_BASE_URL = os.environ.get("DEPLOY_VERIFY_BASE_URL", PRODRONE_SITE_URL).strip() or PRODRONE_SITE_URL
DEPLOY_VERIFY_TIMEOUT = 600   # 초 (Cloudflare Pages 빌드·배포 지연 감안)
DEPLOY_VERIFY_INTERVAL = 30   # 초


# ==========================================
# Gemini 통합 엔진
# ==========================================
class GeminiEngine:
    def __init__(self):
        self.api_key         = GEMINI_API_KEY
        if not self.api_key:
            print("❌ GEMINI_API_KEY 미설정")
            sys.exit(1)
        self.last_call_time  = 0.0
        self.rate_limit_hit  = False

    def _call_api(self, prompt: str, max_tokens: int = 8192, response_mime_type: str = None) -> str:
        if self.rate_limit_hit:
            return ""

        elapsed = time.time() - self.last_call_time
        if elapsed < 7:
            time.sleep(7 - elapsed)
        self.last_call_time = time.time()

        # M7: API 키를 URL 쿼리가 아닌 x-goog-api-key 헤더로 보낸다.
        # 쿼리에 두면 예외 메시지에 URL이 포함될 때 키가 로그에 찍힌다.
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODEL}:generateContent"
        )
        headers = {"x-goog-api-key": self.api_key}
        generation_config = {
            "maxOutputTokens": max_tokens,
            "temperature": 0.4
        }
        if response_mime_type:
            # JSON 출력 호출에만 지정한다. plain-text 재번역·보강 호출에는 쓰지 않는다.
            generation_config["responseMimeType"] = response_mime_type
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": generation_config
        }

        backoff = [15, 30, 60]
        for attempt in range(3):
            try:
                res = requests.post(url, json=payload, headers=headers, timeout=120)

                if res.status_code == 429:
                    wait = backoff[min(attempt, len(backoff) - 1)]
                    print(f"⚠️ 429 Rate Limit (시도 {attempt+1}/3) → {wait}초 대기...")
                    time.sleep(wait)
                    if attempt == 2:
                        print("❌ 429 반복 → 런 종료 (미게시 기사는 다음 런 자동 이월)")
                        self.rate_limit_hit = True
                        return ""
                    continue

                res.raise_for_status()
                candidates = res.json().get("candidates", [])
                if candidates:
                    parts = candidates[0]["content"]["parts"]
                    for part in parts:
                        if not part.get("thought", False) and "text" in part:
                            return part["text"].strip()
                    for part in reversed(parts):
                        if "text" in part:
                            return part["text"].strip()

                print(f"⚠️ Gemini 응답 없음 (시도 {attempt+1}/3)")

            except Exception as e:
                print(f"⚠️ Gemini API 오류 (시도 {attempt+1}/3): {e}")
                if attempt < 2:
                    time.sleep(backoff[attempt])

        return ""

    def translate_article(self, title_ja: str, body_text: str, body_images: list = None) -> dict:
        prompt = f"""당신은 드론/카메라 전문 미디어의 한국어 에디터입니다.
아래 일본어 기사를 한국어로 번역하여 JSON으로만 출력하세요.

★★★ 문체 규칙 (절대 준수) ★★★
본문은 반드시 신문/뉴스 기사 스타일의 평어체(한다체)로 작성하세요.
- 올바른 예: "출시했다", "발표됐다", "제공한다", "낮아진다", "갖추고 있다"
- 절대 금지: "출시했습니다", "발표됩니다", "제공합니다", "낮아집니다" (존댓말 사용 금지)
- 단, [COMMENT]~[/COMMENT] 구간만 예외로 '~입니다', '~합니다' 존댓말 사용
★★★★★★★★★★★★★★★★★★★★

=== 일본어 원문 ===
제목: {title_ja}

본문:
{body_text[:15000]}

=== 번역 규칙 ===
1. 일본어(히라가나·가타카나·한자)를 완전히 한국어로 번역
2. 브랜드명·모델명 원문 유지: Sony, Canon, Nikon, DJI, Blackmagic, Sigma 등
3. 해상도: 4K, 8K, Full HD / 프레임레이트: fps, 24p, 60p
4. 기계 번역 느낌 없이 사람이 쓴 듯 자연스럽게

=== 출력 JSON 규칙 ===
- title: SEO 최적화 제목 (브랜드명·모델명 필수 포함, 최대 50자, 한국어만)
- content: 번역 본문을 순수 Markdown으로 출력 (## 소제목, **굵게**, - 목록 사용, HTML 태그 사용 금지)
- excerpt: 구글 스니펫용 요약 (80~100자, 평어체 필수 — "~다", "~했다"로 끝낼 것)
- tldr: 핵심 요약 3~4항목을 Markdown 목록으로 (- 항목 형식, 평어체 필수)
- 마크다운 백틱 없이 JSON만 출력

{{
  "title": "SEO 제목",
  "content": "## 소제목\\n\\n본문 단락. 이와 같은 기능을 제공한다.\\n\\n## 소제목2\\n\\n출시됐다.",
  "excerpt": "요약문. 이러한 기능을 갖추고 있다.",
  "tldr": "- 요약1이다\\n- 요약2됐다\\n- 요약3한다"
}}"""

        # JSON 출력이므로 responseMimeType을 application/json으로 지정한다
        # (토큰 한도로 잘린 경우 같은 프롬프트 재시도는 또 잘리므로, 애초에 JSON으로 받는다).
        result = self._call_api(prompt, max_tokens=8192, response_mime_type="application/json")
        if not result:
            return {}

        try:
            clean = re.sub(r'```(?:json)?', '', result).strip().rstrip('`').strip()
            match = re.search(r'(\{.*\})', clean, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        except Exception as e:
            print(f"⚠️ JSON 파싱 실패: {e} | 원문: {result[:200]}")

        return {}

    def edit_article(self, title_ko: str, content_ko: str, excerpt: str) -> dict:
        """2회차: SEO 강화 + 문체 다듬기 + 애드센스 품질 기준"""
        prompt = f"""당신은 드론/카메라 전문 미디어의 한국어 시니어 에디터입니다.
아래 한국어 번역 기사를 퇴고·편집하여 JSON으로만 출력하세요.

★★★ 문체 규칙 (절대 준수) ★★★
본문은 반드시 신문/뉴스 기사 스타일의 평어체(한다체)로 작성하세요.
- 올바른 예: "출시했다", "발표됐다", "제공한다", "낮아진다", "갖추고 있다"
- 절대 금지: "출시했습니다", "발표됩니다", "제공합니다", "낮아집니다" (존댓말 사절)
- 단, [COMMENT]~[/COMMENT] 구간만 예외로 '~입니다', '~합니다' 존댓말 사용
★★★★★★★★★★★★★★★★★★★★

=== 번역된 기사 ===
제목: {title_ko}

본문:
{content_ko[:15000]}

요약: {excerpt}

=== 편집 규칙 ===
1. SEO 키워드 강화
   - 제목과 첫 문단에 핵심 키워드(브랜드명·모델명·기능명) 자연스럽게 포함
   - ## 소제목에 키워드 배치
   - 검색 의도에 맞는 자연어 키워드 추가 (예: "가격", "출시일", "스펙", "리뷰")

2. 문체 다듬기
   - 기계번역 느낌 제거 (직역체 → 한국어 자연스러운 표현)
   - 문장 길이 조절 (너무 긴 문장 분리)
   - 본문 전체: 평어체(~다, ~했다, ~이다)로 변환. 존댓말(~입니다, ~합니다)이 남아있으면 반드시 평어체로 바꿀 것
   - [COMMENT]~[/COMMENT] 구간: '~입니다', '~합니다' 존댓말 유지
   - 어색한 조사·어미 교정

3. 애드센스 품질 기준
   - 독창적이고 유용한 정보 중심으로 편집
   - 단순 나열이 아닌 맥락 있는 설명 추가
   - 광고성·스팸성 표현 제거
   - 최소 600자 이상 실질적 내용 유지
   - ★중요★ 본문 끝에 "요약:", "정리:", "결론:" 등의 중복 요약 절대 추가 금지

4. editor_note (한국 시장 심층 분석) ★핵심★
   - 단순 코멘트가 아닌 3~5문단의 실질적 분석을 작성할 것
   - 반드시 다음 관점을 포함:
     ① 한국 드론/로봇 시장에서 이 기술/제품의 의미
     ② 국내 유사 사례 또는 경쟁 현황과 비교
     ③ 한국 규제·정책 환경과의 연관성 (국토교통부, 드론법 등)
     ④ 국내 도입 가능성 또는 실제 활용 시나리오
     ⑤ 향후 한국 시장 전망 및 독자가 주목해야 할 포인트
   - 평어체(~다, ~했다)로 작성, 최소 400자 이상
   - Google 애드센스 기준의 "독창적이고 유용한 콘텐츠"를 충족할 것

=== 출력 JSON 규칙 ===
- title: SEO 최적화 제목 (브랜드명·모델명 필수, 최대 50자, 한국어만)
- content: 편집된 본문을 순수 Markdown으로 출력 (## 소제목, **굵게**, - 목록 사용, HTML 태그 사용 금지)
- excerpt: 구글 스니펫용 요약 (80~100자, 평어체 필수 — "~다", "~했다"로 끝낼 것)
- editor_note: 한국 시장 심층 분석 (3~5문단, 400자 이상, 평어체, Markdown 형식)
- 마크다운 백틱 없이 JSON만 출력

{{
  "title": "편집된 SEO 제목",
  "content": "## 소제목\\n\\n편집된 본문. 이러한 기능을 제공한다.",
  "excerpt": "편집된 요약문. 이러한 기능을 갖추고 있다.",
  "editor_note": "## 한국 시장 전망\\n\\n이 기술은 한국 드론 산업에서 중요한 의미를 갖는다. 국내에서는 이미 유사한 시도가 있었으며...\\n\\n국토교통부의 드론 규제 완화 흐름과 맞물려..."
}}"""

        # JSON 출력이므로 responseMimeType을 application/json으로 지정한다.
        result = self._call_api(prompt, max_tokens=8192, response_mime_type="application/json")
        if not result:
            return {}
        try:
            clean = re.sub(r'```(?:json)?', '', result).strip().rstrip('`').strip()
            match = re.search(r'(\{.*\})', clean, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        except Exception as e:
            print(f"⚠️ 편집 JSON 파싱 실패: {e} | 원문: {result[:200]}")
        return {}

    def expand_thin_content(self, title_ko: str, content_ko: str) -> str:
        """thin content(번역 결과 부족) 보강 요청"""
        prompt = f"""아래 드론/카메라 기사는 본문이 너무 짧습니다.
한국 독자에게 유용한 배경 설명이나 기술 상세를 2~3 문단 추가하여 전체 본문을 반환하세요.
평어체(~다, ~했다)로 작성하고, 기존 내용은 바꾸지 마세요.
제목: {title_ko}

{content_ko[:10000]}"""
        result = self._call_api(prompt, max_tokens=4096)
        return result.strip() if result else content_ko

    def retranslate_content(self, content_ko: str) -> str:
        """일본어 잔존 시 재번역 (긴급용)"""
        prompt = f"""아래 한국어 본문(마크다운)에 일본어가 섞여 있습니다.
일본어 부분만 자연스러운 한국어로 번역하고 전체 본문을 반환하세요.
본문은 평어체(~다, ~했다, ~이다), [COMMENT]~[/COMMENT] 구간은 존댓말(~입니다, ~합니다)로 번역하세요.
★중요★ 마크다운 구조(##, **, -, ![alt](url), <!--more-->)는 절대 깨지지 않게 유지하세요.
본문만 출력:

{content_ko[:15000]}"""
        result = self._call_api(prompt, max_tokens=8192)
        return result if result else content_ko

    def _has_japanese(self, text: str) -> bool:
        plain = BeautifulSoup(text, 'lxml').get_text()
        return len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', plain)) > 5


# ==========================================
# 메인 번역 시스템
# ==========================================
class NewsTranslator:
    def __init__(self):
        self.gemini          = GeminiEngine()
        self.posted_articles = self.load_posted_articles()
        self.setup_hugo_repo()
        # 2단계 중복 방지용: 기존 MD의 source_url 집합 (v9.4.0 이후 발행 글부터 유효)
        self.published_sources = self.scan_published_sources()
        # 수집 소스 상태 (§3-3: 소스 전부 실패 시 런 실패 처리용)
        self._rss_ok = True
        self._archive_ok = True
        # C1: 이번 런에 새로 발행한 글의 슬러그 (배포 검증용)
        self.new_post_slugs = []

    def scan_published_sources(self) -> set:
        """content/posts/*.md front matter에서 source_url을 수집한다. (§3-4 2단계)"""
        sources = set()
        posts_dir = HUGO_REPO_LOCAL / "content/posts"
        if not posts_dir.exists():
            return sources
        for f in posts_dir.glob("*.md"):
            try:
                text = f.read_text(encoding='utf-8')
                m = re.search(r'^source_url:\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
                if m:
                    sources.add(m.group(1).strip())
            except Exception:
                continue
        print(f"📋 기존 발행 원문 URL {len(sources)}건 스캔 완료 (2단계 중복 방지)")
        return sources

    def is_already_published(self, original_url: str) -> bool:
        """2단계 중복 검사: posted JSON(1단계) + MD source_url(2단계)."""
        if not FORCE_UPDATE and original_url in self.posted_articles:
            return True
        if not FORCE_UPDATE and original_url in self.published_sources:
            print(f"⚠️ 중복 감지 (MD source_url) → 스킵: {original_url}")
            return True
        return False

    def setup_hugo_repo(self):
        """Hugo 사이트 레포를 로컬에 클론"""
        if not GITHUB_TOKEN:
            print("⚠️  GITHUB_TOKEN 미설정 → 로컬 저장만 합니다")
            HUGO_REPO_LOCAL.mkdir(parents=True, exist_ok=True)
            (HUGO_REPO_LOCAL / "content/posts").mkdir(parents=True, exist_ok=True)
            (HUGO_REPO_LOCAL / "static/images").mkdir(parents=True, exist_ok=True)
            return
        try:
            if HUGO_REPO_LOCAL.exists():
                subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "pull"], check=True)
            else:
                repo_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{HUGO_SITE_REPO}.git"
                # Step 3 (option B): clone the target branch for an isolated
                # preview test. When the target is "main" the command is
                # exactly the current one (no --branch flag) — behaviour
                # byte-for-byte identical. The push target follows from the
                # checked-out branch, so no push-command change is needed.
                if HUGO_TARGET_BRANCH == "main":
                    subprocess.run(["git", "clone", repo_url, str(HUGO_REPO_LOCAL)], check=True)
                else:
                    subprocess.run(["git", "clone", "--branch", HUGO_TARGET_BRANCH,
                                    repo_url, str(HUGO_REPO_LOCAL)], check=True)
            (HUGO_REPO_LOCAL / "content/posts").mkdir(parents=True, exist_ok=True)
            (HUGO_REPO_LOCAL / "static/images").mkdir(parents=True, exist_ok=True)
            print("✅ Hugo 레포 준비 완료")
        except Exception as e:
            # §3-9: 클론/풀 실패 시 경고만 하고 계속하면 전 기사 발행 실패로 이어진다. 빠른 실패.
            print(f"❌ Hugo 레포 설정 실패 → 런 중단: {e}")
            sys.exit(1)

    def load_posted_articles(self) -> list:
        # §3-4: JSON 손상 시 빈 리스트 반환 금지 — 전체 재처리 트리거가 된다.
        if Path(POSTED_ARTICLES_FILE).exists():
            try:
                data = json.loads(Path(POSTED_ARTICLES_FILE).read_text(encoding='utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"❌ {POSTED_ARTICLES_FILE} 손상 — 파싱 불가: {e}")
                print("   빈 목록으로 진행하면 전체 기사를 재처리하므로 런을 중단합니다.")
                sys.exit(1)
            if not isinstance(data, list):
                print(f"❌ {POSTED_ARTICLES_FILE} 형식이 리스트가 아님 — 런을 중단합니다.")
                sys.exit(1)
            return data
        return []

    def save_posted_articles(self):
        with open(POSTED_ARTICLES_FILE, 'w') as f:
            json.dump(self.posted_articles, f, indent=2)

    @staticmethod
    def _fm_text(s: str) -> str:
        """front matter 문자열 정제 (§3-14): 개행 제거 + 쌍따옴표 치환 + 공백 정리."""
        cleaned = (s or "").replace('"', "'").replace("\r", " ").replace("\n", " ")
        return re.sub(r"\s+", " ", cleaned).strip()

    def _resolve_unique_slug(self, base_slug: str, source_url: str) -> str:
        """슬러그 충돌 해결 (§3-2). 같은 원문 재처리는 덮어쓰기 허용,
        다른 글이면 -2/-3 suffix 부여. 최종 슬러그를 반환한다."""
        posts_dir = HUGO_REPO_LOCAL / "content/posts"
        slug = base_slug
        for n in range(1, 101):
            candidate = base_slug if n == 1 else f"{base_slug}-{n}"
            md_path = posts_dir / f"{candidate}.md"
            if not md_path.exists():
                if n > 1:
                    print(f"   ⚠️ 슬러그 충돌 → 고유 슬러그 사용: {candidate}")
                return candidate
            # 파일이 있으면 원문이 같은지 확인한다
            existing_source = ""
            try:
                text = md_path.read_text(encoding='utf-8')
                m = re.search(r'^source_url:\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
                if m:
                    existing_source = m.group(1).strip()
            except Exception:
                pass
            if source_url and existing_source == source_url:
                print(f"   ℹ️ 동일 원문 재처리 — 기존 파일 덮어쓰기: {candidate}.md")
                return candidate
            # 다른 글의 파일이면 다음 suffix 시도 (기존 파일에 source_url이 없어도 보존)
            slug = candidate
        raise RuntimeError(f"슬러그 충돌 해결 실패 (100회 초과): {base_slug}")

    def publish_to_hugo(self, title: str, content: str, slug: str,
                        excerpt: str, article_date: datetime,
                        featured_image_path: Path = None, source_url: str = ""):
        """Hugo Markdown 파일 생성 + GitHub push.
        성공 시 최종 슬러그(str), 실패 시 None을 반환한다."""
        try:
            # 원문 날짜 유지 + KST 변환
            from datetime import timezone, timedelta
            KST = timezone(timedelta(hours=9))
            dt = article_date
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            else:
                dt = dt.astimezone(KST)
            date_str = dt.strftime('%Y-%m-%dT%H:%M:%S%z')
            date_str = date_str[:-2] + ":" + date_str[-2:]

            # §3-2: 슬러그 충돌 해결 (덮어쓰기 전 존재 검사)
            final_slug = self._resolve_unique_slug(slug, source_url)

            # 이미지 처리
            cover_image = ""
            if featured_image_path and featured_image_path.exists():
                img_dest = HUGO_REPO_LOCAL / "static/images" / featured_image_path.name
                img_dest.write_bytes(featured_image_path.read_bytes())
                cover_image = f"/images/{featured_image_path.name}"

            # §3-14: front matter 값 개행 제거
            fm_title = self._fm_text(title)
            fm_excerpt = self._fm_text(excerpt)

            # Front matter + 본문
            cover_block = f"""cover:
  image: "{cover_image}"
  alt: "{fm_title}"
  relative: false""" if cover_image else ""

            md_content = f"""---
title: "{fm_title}"
date: {date_str}
slug: "{final_slug}"
description: "{fm_excerpt}"
summary: "{fm_excerpt}"
source_url: "{source_url}"
{cover_block}
draft: false
---

{content}
"""
            md_path = HUGO_REPO_LOCAL / "content/posts" / f"{final_slug}.md"
            md_path.write_text(md_content, encoding='utf-8')
            print(f"📝 MD 파일 생성: {md_path.name}")

            if not GITHUB_TOKEN:
                print("⚠️  GITHUB_TOKEN 없음 → 로컬 저장만 완료")
                return final_slug

            # git commit & push
            subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "config", "user.email", "action@github.com"], check=True)
            subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "config", "user.name", "GitHub Action"], check=True)
            subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "add", "."], check=True)
            result = subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "diff", "--cached", "--quiet"], capture_output=True)
            if result.returncode != 0:
                subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "commit", "-m",
                    f"post: {title[:50]} [{article_date.strftime('%Y-%m-%d')}]"] , check=True)
                subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "push"], check=True)
                print(f"✅ GitHub push 완료: {title[:50]}")
            return final_slug

        except Exception as e:
            print(f"❌ Hugo 발행 실패: {e}")
            return None

    def fetch_rss_articles(self) -> list:
        print(f"📡 RSS 피드 확인: {PRONEWS_RSS}")
        try:
            feed = feedparser.parse(PRONEWS_RSS)
        except Exception as e:
            print(f"❌ RSS 파싱 실패: {e}")
            self._rss_ok = False
            return []
        if getattr(feed, "bozo", False):
            print(f"⚠️ RSS 피드 비정상(bozo): {getattr(feed, 'bozo_exception', '')}")
        # #2: feedparser는 네트워크 실패 시에도 예외 없이 bozo=True, entries=0,
        # status=None을 반환하므로, 상태 코드 또는 엔트리 유무로 정상 여부를 판정한다.
        entries = getattr(feed, "entries", []) or []
        self._rss_ok = feed.get("status") == 200 or (bool(entries) and not getattr(feed, "bozo", False))
        if not self._rss_ok:
            print(f"❌ RSS 피드 응답 없음 (status={feed.get('status')}, bozo={getattr(feed, 'bozo', False)}, entries={len(entries)})")
        articles = []
        for entry in feed.entries:
            # entry.link/title 접근도 try 안으로 — 결손 엔트리가 런 전체를 죽이지 않게
            try:
                link = getattr(entry, "link", None)
                title = getattr(entry, "title", None)
                if not link or not title:
                    print(f"   ⚠️ RSS 엔트리 결손 스킵 (link/title 없음): {getattr(entry, 'id', '?')}")
                    continue
                if not FORCE_UPDATE and link in self.posted_articles:
                    continue
                try:
                    article_date = datetime(*entry.published_parsed[:6])
                except Exception:
                    article_date = datetime.now()
            except Exception as e:
                print(f"   ⚠️ RSS 엔트리 처리 오류 스킵: {e}")
                continue
            articles.append({
                'title': title,
                'link': link,
                'date': article_date,
                'source': 'rss'
            })
        print(f"   RSS 미게시: {len(articles)}건")
        return articles

    def fetch_archive_articles(self, need: int, oldest_first: bool = False) -> list:
        print(f"📚 아카이브 크롤링 (필요: {need}건, 오래된순: {oldest_first})...")

        actual_max_page = ARCHIVE_MAX_PAGES
        if oldest_first:
            try:
                print("   🔍 실제 마지막 페이지 번호 탐색 중...")
                res = requests.get(f"{PRONEWS_ARCHIVE_BASE}/1/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'lxml')
                    pages = []
                    for a in soup.find_all('a', href=True):
                        match = re.search(r'/news/page/(\d+)', a['href'])
                        if match:
                            pages.append(int(match.group(1)))
                    if pages:
                        actual_max_page = min(max(pages), ARCHIVE_MAX_PAGES)
                        print(f"   ✅ 탐색된 시작 페이지: {actual_max_page}")
            except Exception as e:
                print(f"   ⚠️ 페이지 탐색 오류 (기본값 {ARCHIVE_MAX_PAGES} 사용): {e}")

        collected = []
        seen_links = set()
        pages_ok = 0
        page = actual_max_page if oldest_first else 1

        while len(collected) < need * 3 and 1 <= page <= ARCHIVE_MAX_PAGES:
            url = f"{PRONEWS_ARCHIVE_BASE}/{page}/"
            try:
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)

                if res.status_code == 404:
                    if oldest_first:
                        print(f"   페이지 {page} 없음 → 이전 페이지 탐색")
                        page -= 1
                        continue
                    else:
                        print(f"   페이지 {page} 없음 → 크롤링 종료")
                        break

                res.raise_for_status()
                pages_ok += 1
                soup = BeautifulSoup(res.text, 'lxml')
                found = []

                # article 태그 기반 파싱
                for article in soup.find_all('article'):
                    a_tag = article.find('a', href=True)
                    if not a_tag:
                        continue
                    link = a_tag['href']
                    if not link.startswith('http'):
                        link = urljoin(PRONEWS_BASE_URL, link)
                    if '/news/' not in link or link in seen_links:
                        continue

                    title_tag = article.find(['h2', 'h3', 'h1'])
                    title = title_tag.get_text(strip=True) if title_tag else a_tag.get_text(strip=True)
                    if not title:
                        continue

                    date_tag = article.find('time')
                    article_date = datetime.now()
                    if date_tag:
                        try:
                            article_date = datetime.fromisoformat(
                                date_tag.get('datetime', date_tag.get_text(strip=True))[:19]
                            )
                        except:
                            pass

                    found.append({'title': title, 'link': link, 'date': article_date, 'source': 'archive'})

                # article 태그 없으면 URL 패턴으로 파싱
                if not found:
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if not href.startswith('http'):
                            href = urljoin(PRONEWS_BASE_URL, href)
                        if re.search(r'/news/\d{10,}', href) and href not in seen_links:
                            title = a.get_text(strip=True)
                            if title and len(title) > 5:
                                found.append({'title': title, 'link': href,
                                              'date': datetime.now(), 'source': 'archive'})

                for art in found:
                    if art['link'] not in seen_links:
                        seen_links.add(art['link'])
                        if FORCE_UPDATE or art['link'] not in self.posted_articles:
                            collected.append(art)

                print(f"   페이지 {page}: {len(found)}건 발견, 누적 미게시: {len(collected)}건")
                page = page - 1 if oldest_first else page + 1
                time.sleep(1)

            except Exception as e:
                print(f"⚠️ 아카이브 페이지 {page} 오류: {e}")
                page = page - 1 if oldest_first else page + 1

        collected.sort(key=lambda x: x['date'], reverse=not oldest_first)
        result = collected[:need]
        print(f"   아카이브 수집 완료: {len(result)}건")
        self._archive_ok = pages_ok > 0
        return result

    def get_articles_to_process(self):
        """처리 대상 기사와 수집 소스 상태를 반환한다. (기사 목록, 수집 실패 여부)"""
        if TARGET_URL:
            print(f"🎯 TARGET_URL 모드: {TARGET_URL}")
            title, dt = self.fetch_title_and_date(TARGET_URL)
            return [{
                'title': title or TARGET_URL,
                'link': TARGET_URL,
                'date': dt or datetime.now(),
                'source': 'single'
            }], False

        if IS_SCHEDULED:
            print("🕐 자동 실행: 최신 우선 + 아카이브 보충")
            rss = self.fetch_rss_articles()
            rss.sort(key=lambda x: x['date'], reverse=True)
            target = rss[:DAILY_LIMIT]
            need = DAILY_LIMIT - len(target)
            if need > 0:
                print(f"   RSS {len(target)}건 → 아카이브에서 {need}건 보충")
                rss_links = {a['link'] for a in target}
                archive = self.fetch_archive_articles(need * 2, oldest_first=False)
                archive = [a for a in archive if a['link'] not in rss_links]
                target += archive[:need]
            target = target[:DAILY_LIMIT]
        else:
            print("📖 수동 실행: 최신 기사 우선 10건")
            rss = self.fetch_rss_articles()
            rss.sort(key=lambda x: x['date'], reverse=True)
            target = rss[:DAILY_LIMIT]
            need = DAILY_LIMIT - len(target)
            if need > 0:
                archive = self.fetch_archive_articles(need * 2, oldest_first=False)
                rss_links = {a['link'] for a in target}
                archive = [a for a in archive if a['link'] not in rss_links]
                target += archive[:need]
            target = target[:DAILY_LIMIT]

        print(f"✅ 처리 대상: {len(target)}건")
        fetch_failed = (not self._rss_ok) and (not self._archive_ok)
        return target, fetch_failed

    def fetch_title_and_date(self, url: str):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'lxml')

            title = ''
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text(strip=True)
            if not title and soup.title:
                title = soup.title.get_text(strip=True)

            article_date = None
            time_tag = soup.find('time', datetime=True)
            if time_tag:
                try:
                    article_date = datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00'))
                except:
                    pass
            return title, article_date
        except:
            return '', None

    def fetch_full_content(self, url: str):
        try:
            print(f"📄 스크래핑: {url}")
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'lxml')

            article_date = None
            time_tag = soup.find('time', datetime=True)
            if time_tag:
                try:
                    article_date = datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00'))
                except:
                    pass

            if not article_date:
                date_text = soup.select_one('.articleHeader-date')
                if date_text:
                    try:
                        article_date = datetime.strptime(date_text.get_text(strip=True)[:10], "%Y.%m.%d")
                    except:
                        pass

            content_div = (
                soup.find('div', class_='post_content') or  # drone.jp 본문
                soup.find('div', class_='entry-content') or
                soup.find('article') or
                soup.find('main')
            )
            if not content_div:
                return "", None, []

            noise_classes = [
                'articleAside', 'mainLayout-side', 'articleShareSticky',
                'articleShare', 'relatedKeyword', 'relatedArticle'
            ]
            for noise_class in noise_classes:
                for noise in content_div.find_all(class_=noise_class):
                    noise.decompose()

            # prnbox(코멘트)는 [COMMENT] 마커로 감싸서 보존
            for prnbox in content_div.find_all(class_='prnbox'):
                prnbox.insert_before(NavigableString('\n[COMMENT]\n'))
                prnbox.insert_after(NavigableString('\n[/COMMENT]\n'))
                prnbox.unwrap()

            removed = False
            for mv_class in ['articleBody-mv', 'article-mv', 'post-thumbnail',
                             'entry-thumbnail', 'article-eye-catch']:
                mv_area = content_div.find(class_=mv_class)
                if mv_area:
                    mv_area.decompose()
                    print(f"🗑️ 본문 상단 이미지 제거 ({mv_class})")
                    removed = True
                    break

            if not removed:
                first_child = content_div.find(recursive=False)
                if first_child and first_child.name in ['figure', 'picture']:
                    first_child.decompose()
                    print("🗑️ 본문 최상단 figure 제거")
                elif first_child and first_child.name == 'img':
                    first_child.decompose()
                    print("🗑️ 본문 최상단 img 제거")
                elif first_child and first_child.name in ['div', 'p']:
                    inner = first_child.find_all(recursive=False)
                    if len(inner) == 1 and inner[0].name in ['img', 'figure', 'picture']:
                        first_child.decompose()
                        print("🗑️ 본문 최상단 이미지 래퍼 제거")

            for elem in content_div.find_all(string=re.compile(
                r'原文掲載時刻:|ソース:|バックナンバー|関連キーワード|この記事をシェア|FOLLOW US'
            )):
                parent = elem.find_parent()
                if parent:
                    parent.decompose()

            for h_tag in content_div.find_all(['h2', 'h3', 'h4']):
                if any(kw in h_tag.get_text(strip=True) for kw in
                       ['バックナンバー', 'この記事をシェア', 'FOLLOW US', '関連記事', '関連キーワード']):
                    next_elem = h_tag.find_next_sibling()
                    h_tag.decompose()
                    while next_elem and next_elem.name not in ['h1', 'h2', 'h3', 'h4']:
                        temp = next_elem.find_next_sibling()
                        next_elem.decompose()
                        next_elem = temp

            for tag in content_div(['script', 'style', 'noscript', 'form', 'nav', 'aside', 'footer', 'header']):
                tag.decompose()

            for iframe in list(content_div.find_all('iframe')):
                if not any(v in iframe.get('src', '').lower() for v in ['youtube', 'youtu.be', 'vimeo']):
                    iframe.decompose()

            for elem in content_div.find_all(class_=lambda x: x and any(
                sc in ' '.join(x).lower() for sc in
                ['social-share', 'share-buttons', 'addtoany', 'sharedaddy', 'entry-footer', 'post-meta']
            )):
                elem.decompose()

            # 본문 이미지 URL 수집 (a 태그 처리 전에 먼저)
            body_images = []
            for img in content_div.find_all('img'):
                src = img.get('src') or img.get('data-src') or ''
                if not src:
                    srcset = img.get('srcset', '')
                    if srcset:
                        src = srcset.split(',')[-1].strip().split(' ')[0]
                src = src.strip()
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(PRONEWS_BASE_URL, src)
                if src and src.startswith('http') and any(
                    ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']
                ):
                    alt = img.get('alt', '')
                    body_images.append({'url': src, 'alt': alt})

            for a in list(content_div.find_all('a')):
                # 이미지 링크는 a만 벗기고 img 유지
                if a.find('img'):
                    a.unwrap()
                    continue

                href = (a.get('href') or '').lower()
                if any(kw in href for kw in
                       ['facebook.com', 'twitter.com', 'line.me', '/fellowship/', 'hatena.ne.jp']) \
                        or href.startswith('//'):
                    a.decompose()
                    continue

                if not a.get_text(strip=True):
                    a.decompose()

            for tag_name in ['p', 'div', 'span', 'li']:
                for tag in content_div.find_all(tag_name):
                    if not tag.get_text(strip=True) and not tag.find('img'):
                        tag.decompose()

            # HTML → 순수 텍스트 변환 (토큰 절약 + Markdown 생성 품질 향상)
            plain_text = content_div.get_text("\n", strip=True)
            plain_text = re.sub(r'\n{3,}', '\n\n', plain_text).strip()

            return plain_text, article_date, body_images

        except Exception as e:
            print(f"⚠️ 스크래핑 실패: {e}")
            return "", None, []

    def get_recent_post_links(self, exclude_slug: str = '', count: int = 3) -> list:
        """Hugo repo의 최근 게시글에서 (title, slug) 목록 반환"""
        posts_dir = HUGO_REPO_LOCAL / "content/posts"
        if not posts_dir.exists():
            return []
        md_files = sorted(posts_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        results = []
        for f in md_files:
            if len(results) >= count:
                break
            try:
                text = f.read_text(encoding='utf-8')
                title_m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
                slug_m  = re.search(r'^slug:\s*["\']?(.+?)["\']?\s*$',  text, re.MULTILINE)
                if not title_m or not slug_m:
                    continue
                slug = slug_m.group(1).strip()
                if slug == exclude_slug:
                    continue
                results.append((title_m.group(1).strip(), slug))
            except Exception:
                continue
        return results

    def generate_seo_slug(self, title_ko: str, article_date: datetime) -> str:
        slug = re.sub(r'[^a-zA-Z0-9\s]', '', title_ko)
        slug = slug.lower().strip().replace(' ', '-')
        slug = re.sub(r'-+', '-', slug).strip('-')
        date_str = article_date.strftime('%Y%m%d') if article_date else datetime.now().strftime('%Y%m%d')
        return f"{slug[:50]}-{date_str}" if len(slug) >= 3 else f"news-{date_str}"

    def get_main_image_url(self, link: str):
        try:
            res = requests.get(link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            soup = BeautifulSoup(res.text, 'lxml')
            og = soup.find('meta', property='og:image')
            if og and og.get('content'):
                return og['content']
            content = (
                soup.find('div', class_='post_content') or
                soup.find('div', class_='entry-content')
            )
            if content:
                img = content.find('img')
                if img:
                    src = img.get('src') or img.get('data-src', '')
                    if src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            src = urljoin(link, src)
                        return src
        except:
            pass
        return None

    def normalize_img_url(self, url: str) -> str:
        """이미지 URL 정규화.
        현재: http:// → https:// 보정 (mixed content 방지)
        나중에 R2/CDN 전환 시 이 함수만 수정하면 됨.
        """
        if url.startswith('http://'):
            url = 'https://' + url[7:]
        return url

    def download_image(self, url: str):
        if not url:
            return None
        try:
            print(f"🖼️ 이미지 다운로드: {url}")
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            res.raise_for_status()
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            ext = os.path.splitext(os.path.basename(urlparse(url).path).split('?')[0])[1]
            if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                ext = '.jpg'
            path = Path(f"/tmp/pronews_{int(time.time())}_{url_hash}{ext}")
            with open(path, 'wb') as f:
                f.write(res.content)
            print(f"   ✅ {path.name}")
            return path
        except Exception as e:
            print(f"⚠️ 이미지 다운로드 실패: {e}")
            return None

    def process_article(self, article: dict) -> str:
        """기사 1건을 처리한다. 결과 상태를 반환한다.
        "published" / "duplicate" / "failed" (#6: 종료 코드 판정용)."""
        print(f"\n{'='*60}")
        print(f"📰 {article['title'][:70]}")
        print(f"📅 {article['date'].strftime('%Y-%m-%d %H:%M')} [{article.get('source','?')}]")
        print(f"{'='*60}")

        if self.gemini.rate_limit_hit:
            print("🛑 429 플래그 → 다음 런 이월")
            return "failed"

        # §3-4: 2단계 중복 검사 (posted JSON + MD source_url)
        if self.is_already_published(article['link']):
            if article['link'] not in self.posted_articles:
                self.posted_articles.append(article['link'])
                self.save_posted_articles()
            print("⏭️  이미 게시됨 → 스킵")
            return "duplicate"

        body_text, exact_date, body_images = self.fetch_full_content(article['link'])
        if not body_text:
            print("⚠️ 본문 스크래핑 실패 → 스킵")
            return "failed"

        if exact_date:
            article['date'] = exact_date
            print(f"🕒 원문 시각 복원 성공: {exact_date.strftime('%Y-%m-%d %H:%M:%S')}")

        # 본문 이미지 목록 출력
        if body_images:
            print(f"🖼️ 본문 이미지 {len(body_images)}개 감지")

        print("🔄 [1단계] Gemini 번역 (1회 JSON 통합)...")
        translated = self.gemini.translate_article(article['title'], body_text, body_images)

        if not translated or not translated.get('title') or not translated.get('content'):
            print("❌ 번역 실패 → 스킵")
            return "failed"

        title_ko    = translated['title']
        content_ko  = translated['content']
        excerpt     = translated.get('excerpt', '')
        tldr_html   = translated.get('tldr', '')
        print(f"   📌 제목: {title_ko}")

        # [4] thin content 체크 — 600자 미만이면 보강 1회 시도
        if len(content_ko.replace('\n', '').replace(' ', '')) < 600:
            print("   ⚠️ thin content 감지 → 보강 요청...")
            content_ko = self.gemini.expand_thin_content(title_ko, content_ko)
            if len(content_ko.replace('\n', '').replace(' ', '')) < 400:
                print("❌ 보강 후에도 내용 부족 → 스킵")
                return "failed"

        if self.gemini._has_japanese(content_ko):
            print("   ⚠️ 일본어 잔존 → 재번역 1회 시도...")
            content_ko = self.gemini.retranslate_content(content_ko)
            if self.gemini._has_japanese(content_ko):
                print("   ⚠️ 재번역 후 일부 잔존 → 경고 후 계속 진행")

        print("✏️  [2단계] Gemini 편집 (SEO·문체·애드센스 품질)...")
        edited = self.gemini.edit_article(title_ko, content_ko, excerpt)
        if edited and edited.get('title') and edited.get('content'):
            title_ko    = edited['title']
            content_ko  = edited['content']
            excerpt     = edited.get('excerpt', excerpt)
            editor_note = edited.get('editor_note', '').strip()
            print(f"   ✅ 편집 완료: {title_ko}")
        else:
            print("   ⚠️ 편집 실패 → 번역본 그대로 사용")
            editor_note = ''

        slug = self.generate_seo_slug(title_ko, article['date'])
        print(f"🔗 Slug: {slug}")

        print("🔍 대표 이미지 처리 중...")
        local_img = None
        img_url = self.get_main_image_url(article['link'])
        if img_url:
            local_img = self.download_image(img_url)

        final_content = ""

        # excerpt + <!--more--> → 썸네일이 핵심요약/editor_note 노출 방지
        if excerpt:
            final_content += f"{excerpt}\n\n<!--more-->\n\n"

        # [1] 한국 시장 분석 섹션 삽입
        if editor_note:
            final_content += f"## 🇰🇷 한국 시장 분석\n\n{editor_note}\n\n---\n\n"

        # excerpt는 front matter의 description으로 이미 표시됨 → 본문 중복 제거
        if tldr_html:
            final_content += "## 💡 핵심 요약\n\n"
            final_content += tldr_html.strip() + "\n\n"
            final_content += "---\n\n"

        # 본문 이미지: 외부 URL 그대로 삽입 (대표 이미지만 로컬 저장)
        # ※ 본문 이미지 로컬화 시 GitHub 무료 용량(1GB) 초과 리스크 있어 외부 링크 유지
        if body_images and "![" not in content_ko:
            paragraphs = content_ko.split('\n\n')
            total = len(paragraphs)
            imgs = body_images[:5]
            insert_positions = sorted(set([
                max(1, total // (len(imgs) + 1) * (i + 1))
                for i in range(len(imgs))
            ]), reverse=True)
            for pos, img in zip(insert_positions, reversed(imgs)):
                img_md = f"\n\n![{img['alt']}]({self.normalize_img_url(img['url'])})\n\n"
                paragraphs.insert(min(pos, len(paragraphs)), img_md)
            content_ko = '\n\n'.join(paragraphs)

        final_content += content_ko

        # [2] 내부링크: 최근 게시글 3개 삽입
        recent_links = self.get_recent_post_links(exclude_slug=slug, count=3)
        if recent_links:
            final_content += "\n\n---\n\n## 📌 관련 기사\n\n"
            for r_title, r_slug in recent_links:
                final_content += f"- [{r_title}](/posts/{r_slug}/)\n"

        # [5] proDRONE.kr 자체 제작 문구
        final_content += (
            "\n\n---\n\n"
            "> 본 기사는 **proDRONE.kr** 편집팀이 해외 드론 산업 동향을 취재·분석하여 "
            "한국 독자를 위해 작성한 콘텐츠입니다."
        )

        print(f"📤 [3단계] Hugo MD 파일 생성 + GitHub push 중...")

        # [COMMENT]~[/COMMENT] 마커를 따옴표로 변환 (자연스러운 인용문 표시)
        final_content = re.sub(r'\s*\[COMMENT\]\s*', '\n\n"', final_content)
        final_content = re.sub(r'\s*\[/COMMENT\]\s*', '"\n\n', final_content)
        final_content = re.sub(r'\n{3,}', '\n\n', final_content).strip()


        final_slug = self.publish_to_hugo(title_ko, final_content, slug, excerpt,
                                article['date'], local_img, source_url=article['link'])
        if final_slug:
            # C1: 이번 런에 발행한 슬러그를 모아 런 종료 시 라이브 URL을 검증한다.
            self.new_post_slugs.append(final_slug)
            if local_img:
                try: local_img.unlink()
                except: pass
            if not FORCE_UPDATE:
                self.posted_articles.append(article['link'])
                self.save_posted_articles()
                self.published_sources.add(article['link'])
            return "published"
        return "failed"

    def run(self) -> int:
        """실행하고 종료 코드를 반환한다. 0=성공, 1=실패. (§3-3)"""
        print(f"\n{'='*60}")
        print(f"DRONE.jp → proDRONE.kr 자동 번역 v9.4.0")
        print(f"엔진: {GEMINI_MODEL} | 호출: 기사당 번역+편집 2회")
        print(f"모드: {'자동 (최신→아카이브 보충)' if IS_SCHEDULED else '수동 (최신 기사 우선)'}")
        print(f"실행 모드: {EFFECTIVE_EVENT} (override={os.environ.get('RUN_MODE_OVERRIDE', '').strip() or 'none'})")
        print(f"발행: Hugo MD → GitHub push | 일일 한도: {DAILY_LIMIT}건")
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        if not GITHUB_TOKEN:
            print("⚠️  GITHUB_TOKEN 없음 → 로컬 저장 모드로 실행")

        print("🔑 Gemini API 키 검증...")
        test = self.gemini._call_api("テストを 한국어로 번역:", max_tokens=30)
        if not test:
            print("❌ Gemini API 키 오류 → 종료")
            return 1
        print(f"   ✅ API 정상: '{test}'")

        articles, fetch_failed = self.get_articles_to_process()
        if fetch_failed:
            print("❌ 수집 소스(RSS+아카이브) 전부 실패 → 런 실패 처리")
            return 1
        if not articles:
            print("✅ 처리할 기사 없음 (신규 기사 없음 — 정상 종료)")
            return 0

        self.new_post_slugs = []
        counts = {"published": 0, "duplicate": 0, "failed": 0}
        try:
            for i, article in enumerate(articles, 1):
                if self.gemini.rate_limit_hit:
                    print(f"\n🛑 429 런 종료 → 남은 {len(articles)-i+1}건 다음 런 이월")
                    break
                print(f"\n[{i}/{len(articles)}]")
                # #7과 같은 취지: 기사 단위 try/except — 한 기사의 예상 못 한 예외가
                # 런 전체를 죽이지 않게.
                try:
                    outcome = self.process_article(article)
                except Exception as e:
                    print(f"❌ 기사 처리 중 예상 못 한 예외 ({article.get('link', '?')}): {e}")
                    outcome = "failed"
                if outcome not in counts:
                    outcome = "failed"
                counts[outcome] += 1
                if i < len(articles):
                    time.sleep(10)
        except Exception as e:
            print(f"❌ 런 루프 중 예상 못 한 예외: {e}")
            counts["failed"] += 1
        finally:
            print(f"\n{'='*60}")
            print(f"🏁 완료: 게시 {counts['published']} / 중복 {counts['duplicate']} / "
                  f"실패 {counts['failed']} (대상 {len(articles)}건)")
            print(f"{'='*60}\n")

        # C1: 배포 검증 — 이번 런에 새로 발행한 글의 라이브 URL이 HTTP 200인지 확인한다.
        # push는 기사마다 이미 끝났고, Pages 빌드·배포 지연을 감안해 시간 창 안에서 재시도한다.
        if self.new_post_slugs:
            if not self.verify_deployment():
                print("❌ 배포 검증 실패 → 런 실패 처리")
                return 1
        # #6: 실제 실패가 있고 게시 0건일 때만 exit 1.
        # 전부 중복이면 정상 종료(0) — 이미 게시된 TARGET_URL도 실패가 아니다.
        if counts["failed"] > 0 and counts["published"] == 0:
            print(f"❌ 실제 실패 {counts['failed']}건, 게시 0건 → 런 실패 처리")
            return 1
        return 0

    def verify_deployment(self) -> bool:
        """C1: 이번 런에 새로 발행한 글의 라이브 URL이 HTTP 200인지 확인한다.
        Cloudflare Pages 빌드·배포 지연을 감안해 DEPLOY_VERIFY_TIMEOUT까지 재시도한다.
        하나라도 200이 아니면 False를 반환한다."""
        urls = [f"{DEPLOY_VERIFY_BASE_URL}/posts/{slug}/" for slug in self.new_post_slugs]
        print(f"🔍 배포 검증: {len(urls)}건 (최대 {DEPLOY_VERIFY_TIMEOUT}초 대기)")
        deadline = time.time() + DEPLOY_VERIFY_TIMEOUT
        pending = list(urls)
        while pending:
            remaining = []
            for url in pending:
                try:
                    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                    if res.status_code == 200:
                        print(f"   ✅ 배포 검증 통과 (HTTP 200): {url}")
                    else:
                        print(f"   ⏳ 배포 검증 대기 (HTTP {res.status_code}): {url}")
                        remaining.append(url)
                except Exception as e:
                    print(f"   ⏳ 배포 검증 대기 (오류): {url} — {e}")
                    remaining.append(url)
            pending = remaining
            if not pending:
                return True
            if time.time() >= deadline:
                for url in pending:
                    print(f"   ❌ 배포 검증 실패 ({DEPLOY_VERIFY_TIMEOUT}초 내 200 없음): {url}")
                return False
            time.sleep(DEPLOY_VERIFY_INTERVAL)
        return True


def main() -> int:
    bot = NewsTranslator()
    return bot.run()


if __name__ == "__main__":
    sys.exit(main())
