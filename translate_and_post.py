#!/usr/bin/env python3
"""
일본 드론 뉴스 자동 번역 및 워드프레스 게시 시스템 (개선판)
- 기능: 전체 본문 스크래핑, 이미지 본문 삽입, 강제 업데이트 모드 지원
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
from bs4 import BeautifulSoup  # HTML 파싱을 위해 추가

# ==========================================
# 설정 (Settings)
# ==========================================
WORDPRESS_URL = "https://grv.co.kr/wp"
WORDPRESS_USER = os.environ.get("WP_USER")
WORDPRESS_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
DRONE_JP_RSS = "https://drone.jp/feed"
POSTED_ARTICLES_FILE = "posted_articles.json"

# [수정 2] 덮어쓰기 모드 (True로 설정하면 이미 올린 글도 다시 번역해서 새 글로 등록함)
FORCE_UPDATE = True 

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
        """RSS 피드 가져오기"""
        print(f"📡 RSS 피드 확인 중: {DRONE_JP_RSS}")
        feed = feedparser.parse(DRONE_JP_RSS)
        
        # 30일 이내 기사까지 허용 (기간 늘림)
        limit_date = datetime.now() - timedelta(days=30)
        recent_articles = []
        
        print(f"🔍 총 {len(feed.entries)}개의 피드 항목 검색 시작...")

        for entry in feed.entries[:10]:  # 최신 10개만 집중 처리
            # [수정 2] FORCE_UPDATE가 꺼져있을 때만 중복 체크
            if not FORCE_UPDATE and entry.link in self.posted_articles:
                print(f"  Pass (이미 게시됨): {entry.title}")
                continue
                
            article_date = datetime(*entry.published_parsed[:6])
            if article_date > limit_date:
                recent_articles.append({
                    'title': entry.title,
                    'link': entry.link,
                    'date': article_date
                })
        
        print(f"✅ 처리할 새 기사: {len(recent_articles)}개")
        return recent_articles
        
    def fetch_full_content(self, url):
        """
        [수정 1] BeautifulSoup을 사용하여 실제 기사 본문 전체 스크래핑
        """
        try:
            print(f"📄 기사 원문 스크래핑 중: {url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # drone.jp 및 일반적인 워드프레스 사이트의 본문 영역 클래스 찾기
            # 사이트마다 다르지만 보통 entry-content, post-content 등을 사용함
            content_div = soup.find('div', class_='entry-content')
            if not content_div:
                content_div = soup.find('div', class_='post-content')
            if not content_div:
                content_div = soup.find('article')
                
            if not content_div:
                print("⚠️ 본문 영역을 찾지 못했습니다. RSS 요약본을 사용합니다.")
                return None

            # 불필요한 태그 제거 (스크립트, 스타일, 광고 등)
            for tag in content_div(['script', 'style', 'iframe', 'noscript', 'form']):
                tag.decompose()
                
            # 텍스트 추출 (HTML 태그를 Markdown 스타일로 변환하기 위해 html2text 사용 준비)
            return str(content_div) # HTML 문자열 반환
            
        except Exception as e:
            print(f"⚠️ 본문 가져오기 실패: {e}")
            return None

    def translate_text(self, text):
        """번역 함수 (오류 처리 강화)"""
        if not text: return ""
        
        try:
            # HTML을 텍스트로 변환 (이미지 태그 등은 유지되지 않음 -> 텍스트 위주 번역)
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True # 이미지는 별도로 처리하므로 텍스트만
            plain_text = h.handle(text)
            
            # 너무 길면 잘라서 번역 (Google API 제한 대비)
            if len(plain_text) > 4000:
                chunks = [plain_text[i:i+4000] for i in range(0, len(plain_text), 4000)]
                translated_parts = []
                for chunk in chunks:
                    res = self.translator.translate(chunk, src='ja', dest='ko')
                    translated_parts.append(res.text)
                    time.sleep(1)
                return "\n".join(translated_parts)
            else:
                result = self.translator.translate(plain_text, src='ja', dest='ko')
                return result.text
        except Exception as e:
            print(f"⚠️ 번역 중 오류 발생: {e}")
            return text  # 실패 시 원문 반환

    def download_image(self, url):
        """이미지 다운로드"""
        if not url: return None
        try:
            print(f"🖼️ 이미지 다운로드: {url}")
            res = requests.get(url, timeout=15)
            if res.status_code == 200:
                filename = os.path.basename(urlparse(url).path)
                if not filename: filename = "image.jpg"
                path = Path(f"/tmp/{filename}")
                with open(path, 'wb') as f:
                    f.write(res.content)
                return path
        except Exception as e:
            print(f"⚠️ 이미지 다운로드 에러: {e}")
        return None

    def upload_media(self, image_path):
        """워드프레스 미디어 업로드"""
        if not image_path: return None
        try:
            url = f"{self.wordpress_api}/media"
            headers = {
                'Content-Disposition': f'attachment; filename={image_path.name}',
                'Authorization': 'Basic '  # requests auth will handle this
            }
            with open(image_path, 'rb') as img:
                res = requests.post(
                    url,
                    auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
                    headers=headers,
                    files={'file': img}
                )
                res.raise_for_status()
                return res.json() # 전체 JSON 반환 (source_url 등 사용 위해)
        except Exception as e:
            print(f"⚠️ 이미지 업로드 실패: {e}")
            return None

    def get_main_image_url(self, link):
        """Open Graph 등을 통해 대표 이미지 URL 추출"""
        try:
            res = requests.get(link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            soup = BeautifulSoup(res.text, 'lxml')
            
            # 1. Open Graph
            og_img = soup.find('meta', property='og:image')
            if og_img: return og_img['content']
            
            # 2. First Image in content
            img = soup.find('div', class_='entry-content').find('img')
            if img: return img['src']
            
        except:
            pass
        return None

    def post_to_wordpress(self, title, content, featured_media_id):
        """워드프레스 포스트 생성"""
        post_data = {
            'title': title,
            'content': content,
            'status': 'publish',
            'featured_media': featured_media_id if featured_media_id else 0
        }
        
        try:
            res = requests.post(
                f"{self.wordpress_api}/posts",
                auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
                json=post_data
            )
            res.raise_for_status()
            print(f"✨ 게시 성공! 링크: {res.json()['link']}")
            return True
        except Exception as e:
            print(f"❌ 게시 실패: {e}")
            if hasattr(e, 'response'): print(e.response.text)
            return False

    def process_article(self, article):
        print(f"\n📰 처리 시작: {article['title']}")
        
        # 1. 본문 전체 가져오기 [수정 1]
        raw_html = self.fetch_full_content(article['link'])
        if not raw_html:
            print("   본문을 가져오지 못해 건너뜁니다.")
            return False
            
        # 2. 번역 (제목 및 본문)
        # 본문을 HTML 상태에서 텍스트만 뽑아 번역하고 Markdown 형식으로 변환됨
        title_ko = self.translate_text(article['title'])
        content_ko = self.translate_text(raw_html)
        
        # 3. 이미지 처리 [수정 3]
        img_url = self.get_main_image_url(article['link'])
        featured_id = 0
        uploaded_img_url = ""
        
        if img_url:
            local_img = self.download_image(img_url)
            media_info = self.upload_media(local_img)
            if media_info:
                featured_id = media_info['id']
                uploaded_img_url = media_info['source_url']
                # 임시 파일 삭제
                try: os.remove(local_img) 
                except: pass

        # 4. 본문 구성 (이미지 삽입 및 원본 링크)
        # [수정 3] 이미지가 본문에 보이도록 최상단에 img 태그 삽입
        final_content = ""
        if uploaded_img_url:
            final_content += f'<img src="{uploaded_img_url}" alt="{title_ko}" style="width:100%; height:auto; margin-bottom: 20px;" /><br><br>'
        
        final_content += content_ko.replace("\n", "<br>") # 줄바꿈 HTML 처리
        final_content += f"<br><br><hr><p>ℹ️ <strong>원문 기사 보기:</strong> <a href='{article['link']}' target='_blank'>{article['title']}</a></p>"
        
        # 5. 게시
        if self.post_to_wordpress(title_ko, final_content, featured_id):
            if not FORCE_UPDATE: # 강제 업데이트 모드가 아닐 때만 리스트에 추가
                self.posted_articles.append(article['link'])
                self.save_posted_articles()
            return True
        return False

    def run(self):
        print("🚀 뉴스 번역 봇 가동 시작")
        if not WORDPRESS_USER:
            print("❌ 환경 변수 설정 필요 (WP_USER, WP_APP_PASSWORD)")
            return

        articles = self.fetch_rss_feed()
        count = 0
        for article in articles:
            if self.process_article(article):
                count += 1
            time.sleep(3) # 서버 부하 방지
            
        print(f"\n🏁 작업 완료. 총 {count}개 게시됨.")

if __name__ == "__main__":
    bot = NewsTranslator()
    bot.run()
