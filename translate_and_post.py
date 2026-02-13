#!/usr/bin/env python3
"""
drone.jp 자동 번역 및 워드프레스 게시 시스템 (개선판 v2)
- 개선 1: 원본 게시일/시간 유지 + 최신순 정렬
- 개선 2: 이미지 중복 제거 (Featured Image만 사용)
- 개선 3: 과거 기사 순차 번역 (매일 10개씩)
- 개선 4: drone.jp 디자인 유사 (CSS 포함)
"""

import os
import sys
import requests
import feedparser
from datetime import datetime, timedelta
from pathlib import Path
import json
import time
from urllib.parse import urlparse, urljoin
from googletrans import Translator
import html2text
from bs4 import BeautifulSoup

# ==========================================
# 설정 (Settings)
# ==========================================
WORDPRESS_URL = "https://grv.co.kr/wp"
WORDPRESS_USER = os.environ.get("WP_USER")
WORDPRESS_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
DRONE_JP_RSS = "https://drone.jp/feed"
POSTED_ARTICLES_FILE = "posted_articles.json"

# [개선 3] 매일 처리할 기사 개수
DAILY_LIMIT = 10

# 강제 재번역 모드 (True로 설정하면 이미 올린 글도 다시 번역)
# GitHub Actions Secrets에서 FORCE_UPDATE=true 설정 가능
FORCE_UPDATE = os.environ.get("FORCE_UPDATE", "false").lower() == "true"

class NewsTranslator:
    def __init__(self):
        self.translator = Translator()
        self.wordpress_api = f"{WORDPRESS_URL}/wp-json/wp/v2"
        self.posted_articles = self.load_posted_articles()
        
    def load_posted_articles(self):
        """이미 게시된 기사 목록 로드"""
        if Path(POSTED_ARTICLES_FILE).exists():
            with open(POSTED_ARTICLES_FILE, 'r') as f:
                try:
                    return json.load(f)
                except:
                    return []
        return []
        
    def save_posted_articles(self):
        """게시된 기사 목록 저장"""
        with open(POSTED_ARTICLES_FILE, 'w') as f:
            json.dump(self.posted_articles, f, indent=2)
        
    def fetch_rss_feed(self):
        """
        [개선 3] RSS 피드에서 미번역 기사 가져오기
        - 오래된 것부터 처리 (과거 기사 순차 번역)
        """
        print(f"📡 RSS 피드 확인 중: {DRONE_JP_RSS}")
        feed = feedparser.parse(DRONE_JP_RSS)
        
        all_articles = []
        print(f"🔍 총 {len(feed.entries)}개의 피드 항목 검색...")

        for entry in feed.entries:
            # 강제 업데이트 모드가 아닐 때만 중복 체크
            if not FORCE_UPDATE and entry.link in self.posted_articles:
                continue
                
            try:
                article_date = datetime(*entry.published_parsed[:6])
            except:
                article_date = datetime.now()
                
            all_articles.append({
                'title': entry.title,
                'link': entry.link,
                'date': article_date
            })
        
        # [개선 3] 오래된 순으로 정렬 (과거 기사부터 번역)
        all_articles.sort(key=lambda x: x['date'])
        
        print(f"✅ 미번역 기사: {len(all_articles)}개 (오래된 것부터 {DAILY_LIMIT}개 처리)")
        return all_articles[:DAILY_LIMIT]
        
    def fetch_full_content(self, url):
        """기사 본문 전체 스크래핑"""
        try:
            print(f"📄 기사 스크래핑: {url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # drone.jp 본문 영역
            content_div = soup.find('div', class_='entry-content')
            if not content_div:
                content_div = soup.find('div', class_='post-content')
            if not content_div:
                content_div = soup.find('article')
                
            if not content_div:
                print("⚠️ 본문 영역을 찾지 못했습니다.")
                return None

            # 불필요한 태그 제거
            for tag in content_div(['script', 'style', 'iframe', 'noscript', 'form']):
                tag.decompose()
                
            return str(content_div)
            
        except Exception as e:
            print(f"⚠️ 스크래핑 실패: {e}")
            return None

    def translate_text(self, text):
        """번역 함수 (긴 텍스트 분할 처리)"""
        if not text: 
            return ""
        
        try:
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0
            plain_text = h.handle(text)
            
            # 긴 텍스트 분할 번역
            if len(plain_text) > 4000:
                chunks = [plain_text[i:i+4000] for i in range(0, len(plain_text), 4000)]
                translated_parts = []
                for chunk in chunks:
                    res = self.translator.translate(chunk, src='ja', dest='ko')
                    translated_parts.append(res.text)
                    time.sleep(1)
                return "\n\n".join(translated_parts)
            else:
                result = self.translator.translate(plain_text, src='ja', dest='ko')
                time.sleep(0.5)
                return result.text
        except Exception as e:
            print(f"⚠️ 번역 오류: {e}")
            return text

    def download_image(self, url):
        """이미지 다운로드 (안전한 파일명 생성)"""
        if not url: 
            return None
        try:
            print(f"🖼️  이미지 다운로드: {url}")
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            
            # 안전한 파일명 생성 (타임스탬프 + 확장자)
            import hashlib
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            timestamp = int(time.time())
            
            # 확장자 추출
            original_filename = os.path.basename(urlparse(url).path)
            if '?' in original_filename:
                original_filename = original_filename.split('?')[0]
            
            ext = os.path.splitext(original_filename)[1]
            if not ext or ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                ext = '.jpg'
            
            # 안전한 파일명: drone_타임스탬프_해시.확장자
            filename = f"drone_{timestamp}_{url_hash}{ext}"
            
            path = Path(f"/tmp/{filename}")
            with open(path, 'wb') as f:
                f.write(res.content)
            
            print(f"   ✅ 저장: {filename}")
            return path
            
        except Exception as e:
            print(f"⚠️ 이미지 다운로드 실패: {e}")
        return None

    def upload_media(self, image_path):
        """워드프레스 미디어 업로드"""
        if not image_path or not image_path.exists(): 
            return None
        try:
            url = f"{self.wordpress_api}/media"
            with open(image_path, 'rb') as img:
                files = {'file': (image_path.name, img, 'image/jpeg')}
                headers = {'Content-Disposition': f'attachment; filename={image_path.name}'}
                res = requests.post(
                    url,
                    auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
                    headers=headers,
                    files=files
                )
                res.raise_for_status()
                return res.json()
        except Exception as e:
            print(f"⚠️ 업로드 실패: {e}")
        return None

    def get_main_image_url(self, link):
        """대표 이미지 URL 추출"""
        try:
            res = requests.get(link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            soup = BeautifulSoup(res.text, 'lxml')
            
            # Open Graph 이미지
            og_img = soup.find('meta', property='og:image')
            if og_img and og_img.get('content'):
                return og_img['content']
            
            # 본문 첫 이미지
            content = soup.find('div', class_='entry-content')
            if content:
                img = content.find('img')
                if img and img.get('src'):
                    img_url = img['src']
                    if not img_url.startswith('http'):
                        img_url = urljoin(link, img_url)
                    return img_url
        except:
            pass
        return None

    def post_to_wordpress(self, title, content, featured_media_id, original_date):
        """
        [개선 1] 워드프레스 포스트 생성 (원본 게시일 유지)
        """
        post_data = {
            'title': title,
            'content': content,
            'status': 'publish',
            'featured_media': featured_media_id if featured_media_id else 0,
            'date': original_date.strftime('%Y-%m-%dT%H:%M:%S')  # [개선 1] 원본 날짜
        }
        
        try:
            res = requests.post(
                f"{self.wordpress_api}/posts",
                auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
                json=post_data
            )
            res.raise_for_status()
            print(f"✨ 게시 성공! {res.json()['link']}")
            return True
        except Exception as e:
            print(f"❌ 게시 실패: {e}")
            if hasattr(e, 'response'):
                print(f"   {e.response.text[:200]}")
            return False

    def process_article(self, article):
        """기사 처리: 스크래핑 → 번역 → 이미지 → 게시"""
        print(f"\n{'='*70}")
        print(f"📰 {article['title']}")
        print(f"📅 원본 게시일: {article['date'].strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*70}")
        
        # 1. 본문 스크래핑
        raw_html = self.fetch_full_content(article['link'])
        if not raw_html:
            print("   ⚠️  본문 없음 - 건너뜀")
            return False
            
        # 2. 번역
        print(f"🔄 제목 번역...")
        title_ko = self.translate_text(article['title'])
        
        print(f"🔄 본문 번역...")
        content_ko = self.translate_text(raw_html)
        
        # 3. 이미지 처리
        print(f"🔍 이미지 검색...")
        img_url = self.get_main_image_url(article['link'])
        featured_id = 0
        
        if img_url:
            local_img = self.download_image(img_url)
            if local_img:
                media_info = self.upload_media(local_img)
                if media_info:
                    featured_id = media_info['id']
                try: 
                    local_img.unlink()
                except: 
                    pass

        # 4. 본문 구성
        # [개선 2] Featured Image만 사용, 본문에는 이미지 삽입 안 함
        final_content = content_ko.replace("\n", "<br>\n")
        
        # [개선 4] drone.jp 스타일 CSS 적용
        final_content = self.add_drone_style(final_content)
        
        # 원문 링크
        final_content += f"\n\n<hr style='margin: 40px 0 20px 0; border: 0; border-top: 1px solid #e0e0e0;'>\n"
        final_content += f"<p style='font-size: 13px; color: #777;'>"
        final_content += f"<strong>원문:</strong> <a href='{article['link']}' target='_blank' rel='noopener' style='color: #0066cc;'>{article['title']}</a>"
        final_content += f"</p>"
        
        # 5. 게시 (원본 날짜로)
        print(f"📤 워드프레스 게시...")
        if self.post_to_wordpress(title_ko, final_content, featured_id, article['date']):
            # 강제 업데이트 모드가 아닐 때만 기록 저장
            if not FORCE_UPDATE:
                self.posted_articles.append(article['link'])
                self.save_posted_articles()
            return True
        return False

    def add_drone_style(self, content):
        """
        [개선 4] drone.jp 스타일 CSS 적용
        """
        styled = f"""
<div class="drone-article-content" style="
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 16px;
    line-height: 1.8;
    color: #333;
    max-width: 800px;
    margin: 0 auto;
">
{content}
</div>

<style>
.drone-article-content p {{
    margin-bottom: 1.5em;
}}

.drone-article-content h2, .drone-article-content h3 {{
    color: #2c3e50;
    margin-top: 2em;
    margin-bottom: 1em;
    font-weight: 600;
}}

.drone-article-content a {{
    color: #0066cc;
    text-decoration: none;
}}

.drone-article-content a:hover {{
    text-decoration: underline;
}}

.drone-article-content img {{
    max-width: 100%;
    height: auto;
    display: block;
    margin: 2em auto;
}}

.drone-article-content blockquote {{
    border-left: 4px solid #0066cc;
    padding-left: 1.5em;
    margin: 1.5em 0;
    color: #555;
    font-style: italic;
}}
</style>
"""
        return styled

    def run(self):
        """메인 실행"""
        print(f"\n{'🚁'*35}")
        print(f"  drone.jp 자동 번역 시스템 v2")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'🚁'*35}\n")
        
        if not WORDPRESS_USER or not WORDPRESS_APP_PASSWORD:
            print("❌ 환경 변수 필요: WP_USER, WP_APP_PASSWORD")
            sys.exit(1)

        articles = self.fetch_rss_feed()
        
        if not articles:
            print("✅ 모든 기사 번역 완료!")
            return
        
        success_count = 0
        for article in articles:
            if self.process_article(article):
                success_count += 1
            time.sleep(3)
            
        print(f"\n{'='*70}")
        print(f"🏁 완료: {success_count}/{len(articles)}개 게시")
        print(f"📊 남은 미번역 기사: {len([e for e in feedparser.parse(DRONE_JP_RSS).entries if e.link not in self.posted_articles])}개")
        print(f"{'='*70}\n")

if __name__ == "__main__":
    bot = NewsTranslator()
    bot.run()
