#!/usr/bin/env python3
"""
일본 드론 뉴스 자동 번역 및 워드프레스 게시 시스템
- 소스: drone.jp RSS
- 번역: Google Translate API
- 게시: WordPress REST API
"""

import os
import sys
import requests
import feedparser
from datetime import datetime, timedelta
from pathlib import Path
import json
import time
from urllib.parse import urlparse
from googletrans import Translator
import html2text
import re

# 설정
WORDPRESS_URL = "https://grv.co.kr/wp"
WORDPRESS_USER = os.environ.get("WP_USER")
WORDPRESS_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
DRONE_JP_RSS = "https://drone.jp/feed"
POSTED_ARTICLES_FILE = "posted_articles.json"

class NewsTranslator:
    def __init__(self):
        self.translator = Translator()
        self.wordpress_api = f"{WORDPRESS_URL}/wp-json/wp/v2"
        self.posted_articles = self.load_posted_articles()
        
    def load_posted_articles(self):
        """이미 게시된 기사 목록 로드"""
        if Path(POSTED_ARTICLES_FILE).exists():
            with open(POSTED_ARTICLES_FILE, 'r') as f:
                return json.load(f)
        return []
    
    def save_posted_articles(self):
        """게시된 기사 목록 저장"""
        with open(POSTED_ARTICLES_FILE, 'w') as f:
            json.dump(self.posted_articles, f, indent=2)
    
    def fetch_rss_feed(self):
        """RSS 피드에서 최신 기사 가져오기"""
        print(f"📡 RSS 피드 확인 중: {DRONE_JP_RSS}")
        feed = feedparser.parse(DRONE_JP_RSS)
        
        # 7일 이내 기사만
        yesterday = datetime.now() - timedelta(days=7)
        recent_articles = []
        
        for entry in feed.entries[:30]:  # 최신 30개 체크
            if entry.link in self.posted_articles:
                continue
                
            article_date = datetime(*entry.published_parsed[:6])
            if article_date > yesterday:
                recent_articles.append({
                    'title': entry.title,
                    'link': entry.link,
                    'content': entry.get('summary', ''),
                    'date': article_date
                })
        
        print(f"✅ 새 기사 {len(recent_articles)}개 발견")
        return recent_articles
    
    def translate_text(self, text, max_length=5000):
        """Google Translate로 번역"""
        if not text or len(text.strip()) == 0:
            return ""
        
        # HTML 태그 제거
        h = html2text.HTML2Text()
        h.ignore_links = False
        plain_text = h.handle(text)
        
        # 너무 긴 텍스트는 분할
        if len(plain_text) > max_length:
            plain_text = plain_text[:max_length] + "..."
        
        try:
            result = self.translator.translate(plain_text, src='ja', dest='ko')
            time.sleep(0.5)  # API 제한 방지
            return result.text
        except Exception as e:
            print(f"⚠️ 번역 오류: {e}")
            return plain_text
    
    def fetch_article_content(self, url):
        """기사 본문 전체 가져오기"""
        try:
            print(f"📄 기사 본문 가져오는 중: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # 여기서는 간단히 구현, 실제로는 BeautifulSoup 사용 권장
            return response.text[:2000]  # 일단 앞부분만
        except Exception as e:
            print(f"⚠️ 기사 가져오기 실패: {e}")
            return None
    
    def download_featured_image(self, url):
        """기사의 대표 이미지 다운로드"""
        try:
            print(f"🖼️ 이미지 다운로드 중: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            # 임시 파일로 저장
            filename = Path(url).name
            image_path = Path(f"/tmp/{filename}")
            
            with open(image_path, 'wb') as f:
                f.write(response.content)
            
            return image_path
        except Exception as e:
            print(f"⚠️ 이미지 다운로드 실패: {e}")
            return None
    
    def upload_image_to_wordpress(self, image_path, title):
        """워드프레스에 이미지 업로드"""
        try:
            url = f"{self.wordpress_api}/media"
            
            with open(image_path, 'rb') as img:
                files = {
                    'file': (image_path.name, img, 'image/jpeg')
                }
                headers = {
                    'Content-Disposition': f'attachment; filename="{image_path.name}"'
                }
                
                response = requests.post(
                    url,
                    auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
                    files=files,
                    headers=headers
                )
                response.raise_for_status()
                
                media_id = response.json()['id']
                print(f"✅ 이미지 업로드 완료: ID {media_id}")
                return media_id
        except Exception as e:
            print(f"⚠️ 이미지 업로드 실패: {e}")
            return None
    
    def extract_image_from_content(self, html_content):
        """HTML 컨텐츠에서 첫 번째 이미지 URL 추출"""
        img_pattern = r'<img[^>]+src="([^">]+)"'
        match = re.search(img_pattern, html_content)
        if match:
            return match.group(1)
        return None
    
    def post_to_wordpress(self, title, content, featured_image_id=None):
        """워드프레스에 포스트 게시"""
        url = f"{self.wordpress_api}/posts"
        
        post_data = {
            'title': title,
            'content': content,
            'status': 'publish',
            'format': 'standard'
        }
        
        if featured_image_id:
            post_data['featured_media'] = featured_image_id
        
        try:
            response = requests.post(
                url,
                auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
                json=post_data
            )
            response.raise_for_status()
            
            post_url = response.json()['link']
            print(f"✅ 워드프레스 게시 완료: {post_url}")
            return True
        except Exception as e:
            print(f"❌ 게시 실패: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"   상세: {e.response.text}")
            return False
    
    def process_article(self, article):
        """기사 하나 처리: 번역 + 이미지 + 게시"""
        print(f"\n{'='*60}")
        print(f"📰 처리 중: {article['title']}")
        print(f"{'='*60}")
        
        # 제목 번역
        translated_title = self.translate_text(article['title'])
        print(f"✅ 제목 번역 완료")
        
        # 본문 번역
        translated_content = self.translate_text(article['content'])
        print(f"✅ 본문 번역 완료")
        
        # 원문 링크 추가
        translated_content += f"\n\n---\n**원문 기사:** [{article['link']}]({article['link']})"
        
        # 이미지 처리
        featured_image_id = None
        image_url = self.extract_image_from_content(article['content'])
        
        if image_url:
            # 상대 경로를 절대 경로로 변환
            if not image_url.startswith('http'):
                image_url = f"https://drone.jp{image_url}"
            
            image_path = self.download_featured_image(image_url)
            if image_path:
                featured_image_id = self.upload_image_to_wordpress(image_path, translated_title)
                image_path.unlink()  # 임시 파일 삭제
        
        # 워드프레스에 게시
        success = self.post_to_wordpress(
            translated_title, 
            translated_content,
            featured_image_id
        )
        
        if success:
            self.posted_articles.append(article['link'])
            self.save_posted_articles()
            return True
        
        return False
    
    def run(self):
        """메인 실행 함수"""
        print(f"\n🚀 일본 드론 뉴스 자동 번역 시스템 시작")
        print(f"⏰ 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 인증 확인
        if not WORDPRESS_USER or not WORDPRESS_APP_PASSWORD:
            print("❌ 워드프레스 인증 정보가 없습니다!")
            print("   환경 변수 WP_USER와 WP_APP_PASSWORD를 설정하세요.")
            sys.exit(1)
        
        # RSS 피드에서 새 기사 가져오기
        articles = self.fetch_rss_feed()
        
        if not articles:
            print("ℹ️ 새로운 기사가 없습니다.")
            return
        
        # 각 기사 처리
        success_count = 0
        for article in articles[:10]:  # 한 번에 최대 10개
            if self.process_article(article):
                success_count += 1
            time.sleep(2)  # 각 게시물 사이 대기
        
        print(f"\n{'='*60}")
        print(f"✅ 완료: {success_count}/{len(articles)}개 기사 게시")
        print(f"{'='*60}\n")

if __name__ == "__main__":
    translator = NewsTranslator()
    translator.run()
