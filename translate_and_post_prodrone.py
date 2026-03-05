#!/usr/bin/env python3
"""
DRONE.jp 자동 번역 시스템 v9.3.0
파이프라인: 일본어 원문 → Gemini 번역 → Gemini 편집 → Hugo Markdown → GitHub Push

v9.2.0 → v9.3.0 변경사항:
- 본문 출력 형식: HTML → 순수 Markdown (raw HTML omitted 문제 완전 해결)
- tldr: <ul><li> HTML → - 마크다운 목록
- 제목 한국어 전용 강제 (일본어 잔존 방지)
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
DAILY_LIMIT            = 1
ARCHIVE_MAX_PAGES      = 20

# Hugo 사이트 레포 설정
HUGO_SITE_REPO         = os.environ.get("HUGO_SITE_REPO", "prodg-kr/prodrone")
GITHUB_TOKEN           = os.environ.get("GITHUB_TOKEN")
HUGO_REPO_LOCAL        = Path("/tmp/prodrone-site")

# 실행 모드 감지
GITHUB_EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch")
IS_SCHEDULED      = GITHUB_EVENT_NAME == "schedule"

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# 단일 URL 1개만 처리할 때 사용 (예: https://drone.jp/news/...)
TARGET_URL  = os.environ.get("TARGET_URL", "").strip()


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

    def _call_api(self, prompt: str, max_tokens: int = 8192) -> str:
        if self.rate_limit_hit:
            return ""

        elapsed = time.time() - self.last_call_time
        if elapsed < 7:
            time.sleep(7 - elapsed)
        self.last_call_time = time.time()

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{GEMINI_MODEL}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.4
            }
        }

        backoff = [15, 30, 60]
        for attempt in range(3):
            try:
                res = requests.post(url, json=payload, timeout=120)

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

        result = self._call_api(prompt, max_tokens=8192)
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
   - 최소 300자 이상 실질적 내용 유지
   - ★중요★ 본문 끝에 "요약:", "정리:", "결론:" 등의 중복 요약 절대 추가 금지

=== 출력 JSON 규칙 ===
- title: SEO 최적화 제목 (브랜드명·모델명 필수, 최대 50자, 한국어만)
- content: 편집된 본문을 순수 Markdown으로 출력 (## 소제목, **굵게**, - 목록 사용, HTML 태그 사용 금지)
- excerpt: 구글 스니펫용 요약 (80~100자, 평어체 필수 — "~다", "~했다"로 끝낼 것)
- 마크다운 백틱 없이 JSON만 출력

{{
  "title": "편집된 SEO 제목",
  "content": "## 소제목\\n\\n편집된 본문. 이러한 기능을 제공한다.",
  "excerpt": "편집된 요약문. 이러한 기능을 갖추고 있다."
}}"""

        result = self._call_api(prompt, max_tokens=8192)
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
                subprocess.run(["git", "clone", repo_url, str(HUGO_REPO_LOCAL)], check=True)
            (HUGO_REPO_LOCAL / "content/posts").mkdir(parents=True, exist_ok=True)
            (HUGO_REPO_LOCAL / "static/images").mkdir(parents=True, exist_ok=True)
            print("✅ Hugo 레포 준비 완료")
        except Exception as e:
            print(f"⚠️  Hugo 레포 설정 실패: {e}")

    def load_posted_articles(self) -> list:
        if Path(POSTED_ARTICLES_FILE).exists():
            with open(POSTED_ARTICLES_FILE, 'r') as f:
                try:
                    return json.load(f)
                except:
                    return []
        return []

    def save_posted_articles(self):
        with open(POSTED_ARTICLES_FILE, 'w') as f:
            json.dump(self.posted_articles, f, indent=2)

    def publish_to_hugo(self, title: str, content: str, slug: str,
                        excerpt: str, article_date: datetime,
                        featured_image_path: Path = None) -> bool:
        """Hugo Markdown 파일 생성 + GitHub push"""
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

            # 이미지 처리
            cover_image = ""
            if featured_image_path and featured_image_path.exists():
                img_dest = HUGO_REPO_LOCAL / "static/images" / featured_image_path.name
                img_dest.write_bytes(featured_image_path.read_bytes())
                cover_image = f"/images/{featured_image_path.name}"

            # Front matter + 본문
            cover_block = f"""cover:
  image: "{cover_image}"
  alt: "{title.replace('"', "'")}"
  relative: false""" if cover_image else ""

            md_content = f"""---
title: "{title.replace('"', "'")}"
date: {date_str}
slug: "{slug}"
description: "{excerpt.replace('"', "'")}"
summary: "{excerpt.replace('"', "'")}"
{cover_block}
draft: false
---

{content}
"""
            md_path = HUGO_REPO_LOCAL / "content/posts" / f"{slug}.md"
            md_path.write_text(md_content, encoding='utf-8')
            print(f"📝 MD 파일 생성: {md_path.name}")

            if not GITHUB_TOKEN:
                print("⚠️  GITHUB_TOKEN 없음 → 로컬 저장만 완료")
                return True

            # git commit & push
            subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "config", "user.email", "action@github.com"], check=True)
            subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "config", "user.name", "GitHub Action"], check=True)
            subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "add", "."], check=True)
            result = subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "diff", "--cached", "--quiet"], capture_output=True)
            if result.returncode != 0:
                subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "commit", "-m",
                    f"post: {title[:50]} [{article_date.strftime('%Y-%m-%d')}]"], check=True)
                subprocess.run(["git", "-C", str(HUGO_REPO_LOCAL), "push"], check=True)
                print(f"✅ GitHub push 완료: {title[:50]}")
            return True

        except Exception as e:
            print(f"❌ Hugo 발행 실패: {e}")
            return False

    def fetch_rss_articles(self) -> list:
        print(f"📡 RSS 피드 확인: {PRONEWS_RSS}")
        feed = feedparser.parse(PRONEWS_RSS)
        articles = []
        for entry in feed.entries:
            if not FORCE_UPDATE and entry.link in self.posted_articles:
                continue
            try:
                article_date = datetime(*entry.published_parsed[:6])
            except:
                article_date = datetime.now()
            articles.append({
                'title': entry.title,
                'link': entry.link,
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
        return result

    def get_articles_to_process(self) -> list:
        if TARGET_URL:
            print(f"🎯 TARGET_URL 모드: {TARGET_URL}")
            title, dt = self.fetch_title_and_date(TARGET_URL)
            return [{
                'title': title or TARGET_URL,
                'link': TARGET_URL,
                'date': dt or datetime.now(),
                'source': 'single'
            }]

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
        return target

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

    def commit_posted_articles(self):
        try:
            subprocess.run(['git', 'config', 'user.email', 'action@github.com'], check=True)
            subprocess.run(['git', 'config', 'user.name', 'GitHub Action'], check=True)
            subprocess.run(['git', 'add', POSTED_ARTICLES_FILE], check=True)
            result = subprocess.run(['git', 'diff', '--cached', '--quiet'], capture_output=True)
            if result.returncode != 0:
                subprocess.run(['git', 'commit', '-m',
                    f'chore: update posted_articles [{datetime.now().strftime("%Y-%m-%d %H:%M")}]'], check=True)
                subprocess.run(['git', 'push'], check=True)
                print("📝 posted_articles.json → git 커밋 완료")
        except Exception as e:
            print(f"⚠️ git 커밋 실패: {e}")

    def process_article(self, article: dict) -> bool:
        print(f"\n{'='*60}")
        print(f"📰 {article['title'][:70]}")
        print(f"📅 {article['date'].strftime('%Y-%m-%d %H:%M')} [{article.get('source','?')}]")
        print(f"{'='*60}")

        if self.gemini.rate_limit_hit:
            print("🛑 429 플래그 → 다음 런 이월")
            return False

        if not FORCE_UPDATE and article['link'] in self.posted_articles:
            print("⏭️  이미 게시됨 → 스킵")
            return False

        body_text, exact_date, body_images = self.fetch_full_content(article['link'])
        if not body_text:
            print("⚠️ 본문 스크래핑 실패 → 스킵")
            return False

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
            return False

        title_ko   = translated['title']
        content_ko = translated['content']
        excerpt    = translated.get('excerpt', '')
        tldr_html  = translated.get('tldr', '')
        print(f"   📌 제목: {title_ko}")

        if self.gemini._has_japanese(content_ko):
            print("   ⚠️ 일본어 잔존 → 재번역 1회 시도...")
            content_ko = self.gemini.retranslate_content(content_ko)
            if self.gemini._has_japanese(content_ko):
                print("   ⚠️ 재번역 후 일부 잔존 → 경고 후 계속 진행")

        print("✏️  [2단계] Gemini 편집 (SEO·문체·애드센스 품질)...")
        edited = self.gemini.edit_article(title_ko, content_ko, excerpt)
        if edited and edited.get('title') and edited.get('content'):
            title_ko   = edited['title']
            content_ko = edited['content']
            excerpt    = edited.get('excerpt', excerpt)
            print(f"   ✅ 편집 완료: {title_ko}")
        else:
            print("   ⚠️ 편집 실패 → 번역본 그대로 사용")

        slug = self.generate_seo_slug(title_ko, article['date'])
        print(f"🔗 Slug: {slug}")

        print("🔍 대표 이미지 처리 중...")
        local_img = None
        img_url = self.get_main_image_url(article['link'])
        if img_url:
            local_img = self.download_image(img_url)

        final_content = ""
        # excerpt 1문단 + <!--more--> → 썸네일에 핵심요약 노출 방지
        if excerpt:
            final_content += f"{excerpt}\n\n<!--more-->\n\n"
        if tldr_html:
            final_content += "## 💡 핵심 요약\n\n"
            final_content += tldr_html.strip() + "\n\n"
            final_content += "---\n\n"

        # 본문 이미지를 단락 사이에 균등 삽입 (이미 이미지 있으면 스킵)
        if body_images and "![" not in content_ko:
            paragraphs = content_ko.split('\n\n')
            total = len(paragraphs)
            imgs = body_images[:5]
            # 본문 1/3, 2/3 지점에 이미지 삽입
            insert_positions = sorted(set([
                max(1, total // (len(imgs) + 1) * (i + 1))
                for i in range(len(imgs))
            ]), reverse=True)
            for pos, img in zip(insert_positions, reversed(imgs)):
                img_md = f"\n\n![{img['alt']}]({img['url']})\n\n"
                paragraphs.insert(min(pos, len(paragraphs)), img_md)
            content_ko = '\n\n'.join(paragraphs)

        final_content += content_ko
        final_content += (
            "\n\n---\n\n"
            f"**원문:** [{article['title']}]({article['link']})"
        )

        print(f"📤 [3단계] Hugo MD 파일 생성 + GitHub push 중...")

        # [COMMENT]~[/COMMENT] 마커를 따옴표로 변환 (자연스러운 인용문 표시)
        final_content = re.sub(r'\s*\[COMMENT\]\s*', '\n\n"', final_content)
        final_content = re.sub(r'\s*\[/COMMENT\]\s*', '"\n\n', final_content)
        final_content = re.sub(r'\n{3,}', '\n\n', final_content).strip()


        if self.publish_to_hugo(title_ko, final_content, slug, excerpt,
                                article['date'], local_img):
            if local_img:
                try: local_img.unlink()
                except: pass
            if not FORCE_UPDATE:
                self.posted_articles.append(article['link'])
                self.save_posted_articles()
            return True
        return False

    def run(self):
        print(f"\n{'='*60}")
        print(f"DRONE.jp → proDRONE.kr 자동 번역 v9.0.0")
        print(f"엔진: {GEMINI_MODEL} | 호출: 기사당 1회 JSON 통합")
        print(f"모드: {'자동 (최신→아카이브 보충)' if IS_SCHEDULED else '수동 (아카이브 오래된 순)'}")
        print(f"발행: Hugo MD → GitHub push | 일일 한도: {DAILY_LIMIT}건")
        print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        if not GITHUB_TOKEN:
            print("⚠️  GITHUB_TOKEN 없음 → 로컬 저장 모드로 실행")

        print("🔑 Gemini API 키 검증...")
        test = self.gemini._call_api("テスト를 한국어로 번역:", max_tokens=30)
        if not test:
            print("❌ Gemini API 키 오류 → 종료")
            sys.exit(1)
        print(f"   ✅ API 정상: '{test}'")

        articles = self.get_articles_to_process()
        if not articles:
            print("✅ 처리할 기사 없음")
            return

        success = 0
        try:
            for i, article in enumerate(articles, 1):
                if self.gemini.rate_limit_hit:
                    print(f"\n🛑 429 런 종료 → 남은 {len(articles)-i+1}건 다음 런 이월")
                    break
                print(f"\n[{i}/{len(articles)}]")
                if self.process_article(article):
                    success += 1
                if i < len(articles):
                    time.sleep(10)
        finally:
            print(f"\n{'='*60}")
            print(f"🏁 완료: {success}/{len(articles)}건 게시")
            print(f"{'='*60}\n")


if __name__ == "__main__":
    bot = NewsTranslator()
    bot.run()
