#!/usr/bin/env python3
"""
drone.jp 자동 번역 - 긴급 재게시 버전
FORCE_UPDATE = True 로 설정됨
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
import hashlib

# ==========================================
# 설정
# ==========================================
WORDPRESS_URL = "https://grv.co.kr/wp"
WORDPRESS_USER = os.environ.get("WP_USER")
WORDPRESS_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD")
DRONE_JP_RSS = "https://drone.jp/feed"
POSTED_ARTICLES_FILE = "posted_articles.json"
DAILY_LIMIT = 10

# ⚠️ 긴급: 강제 재번역 모드 활성화
FORCE_UPDATE = True  # ← 모든 기사 다시 번역!

print(f"⚠️ FORCE_UPDATE 모드: {FORCE_UPDATE}")

class NewsTranslator:
    def __init__(self):
        self.translator = Translator()
        self.wordpress_api = f"{WORDPRESS_URL}/wp-json/wp/v2"
        self.posted_articles = self.load_posted_articles()
        
    def load_posted_articles(self):
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
        
    def fetch_rss_feed(self):
        print(f"📡 RSS 피드 확인 중: {DRONE_JP_RSS}")
        feed = feedparser.parse(DRONE_JP_RSS)
        
        all_articles = []
        print(f"🔍 총 {len(feed.entries)}개의 피드 항목 검색...")

        for entry in feed.entries:
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
        
        all_articles.sort(key=lambda x: x['date'])
        
        print(f"✅ 처리할 기사: {len(all_articles)}개 (최대 {DAILY_LIMIT}개 처리)")
        return all_articles[:DAILY_LIMIT]
        
    def fetch_full_content(self, url):
        try:
            print(f"📄 스크래핑: {url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            content_div = soup.find('div', class_='entry-content')
            if not content_div:
                content_div = soup.find('article')
                
            if not content_div:
                return None

            for tag in content_div(['script', 'style', 'iframe', 'noscript', 'form']):
                tag.decompose()
                
            return str(content_div)
        except Exception as e:
            print(f"⚠️ 실패: {e}")
            return None

    def translate_text(self, text):
        if not text: 
            return ""
        
        try:
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            h.body_width = 0
            plain_text = h.handle(text)
            
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
        if not url: 
            return None
        try:
            print(f"🖼️ 다운로드: {url}")
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            
            # 안전한 파일명 생성
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            timestamp = int(time.time())
            
            original_filename = os.path.basename(urlparse(url).path)
            if '?' in original_filename:
                original_filename = original_filename.split('?')[0]
            
            ext = os.path.splitext(original_filename)[1]
            if not ext or ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                ext = '.jpg'
            
            filename = f"drone_{timestamp}_{url_hash}{ext}"
            path = Path(f"/tmp/{filename}")
            
            with open(path, 'wb') as f:
                f.write(res.content)
            
            print(f"   ✅ {filename}")
            return path
        except Exception as e:
            print(f"⚠️ 실패: {e}")
        return None

    def upload_media(self, image_path):
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
        try:
            res = requests.get(link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            soup = BeautifulSoup(res.text, 'lxml')
            
            og_img = soup.find('meta', property='og:image')
            if og_img and og_img.get('content'):
                return og_img['content']
            
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
        post_data = {
            'title': title,
            'content': content,
            'status': 'publish',
            'featured_media': featured_media_id if featured_media_id else 0,
            'date': original_date.strftime('%Y-%m-%dT%H:%M:%S')
        }
        
        try:
            res = requests.post(
                f"{self.wordpress_api}/posts",
                auth=(WORDPRESS_USER, WORDPRESS_APP_PASSWORD),
                json=post_data
            )
            res.raise_for_status()
            print(f"✨ 게시 성공!")
            return True
        except Exception as e:
            print(f"❌ 실패: {e}")
            return False

    def process_article(self, article):
        print(f"\n{'='*60}")
        print(f"📰 {article['title'][:50]}...")
        print(f"{'='*60}")
        
        raw_html = self.fetch_full_content(article['link'])
        if not raw_html:
            return False
            
        print(f"🔄 번역 중...")
        title_ko = self.translate_text(article['title'])
        content_ko = self.translate_text(raw_html)
        
        print(f"🔍 이미지...")
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

        final_content = content_ko.replace("\n", "<br>\n")
        final_content += f"\n\n<hr><p style='font-size:13px;color:#777;'>"
        final_content += f"<strong>원문:</strong> <a href='{article['link']}' target='_blank'>{article['title']}</a></p>"
        
        print(f"📤 게시...")
        if self.post_to_wordpress(title_ko, final_content, featured_id, article['date']):
            if not FORCE_UPDATE:
                self.posted_articles.append(article['link'])
                self.save_posted_articles()
            return True
        return False

    def run(self):
        print(f"\n{'='*60}")
        print(f"drone.jp 자동 번역 (강제 모드)")
        print(f"{'='*60}\n")
        
        if not WORDPRESS_USER or not WORDPRESS_APP_PASSWORD:
            print("❌ 환경 변수 필요!")
            sys.exit(1)

        articles = self.fetch_rss_feed()
        
        if not articles:
            print("✅ 처리할 기사 없음")
            return
        
        success = 0
        for article in articles:
            if self.process_article(article):
                success += 1
            time.sleep(3)
            
        print(f"\n{'='*60}")
        print(f"🏁 완료: {success}/{len(articles)}개")
        print(f"{'='*60}\n")

if __name__ == "__main__":
    bot = NewsTranslator()
    bot.run()
