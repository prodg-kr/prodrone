# drone.jp 자동 번역 시스템 개선사항 (v2)

## ✅ 적용된 4가지 개선사항

### 1. 원본 게시일/시간 유지 + 최신순 자동 정렬

**변경 내용:**
```python
# WordPress REST API의 'date' 파라미터 사용
post_data = {
    'date': original_date.strftime('%Y-%m-%dT%H:%M:%S')
}
```

**효과:**
- ✅ 기사가 원본 drone.jp의 게시 시간으로 표시됨
- ✅ WordPress에서 자동으로 최신순 정렬 (별도 설정 불필요)
- ✅ 검색 엔진 최적화(SEO)에 유리

---

### 2. 이미지 중복 제거

**변경 내용:**
```python
# Featured Image만 사용 (본문에 이미지 삽입 제거)
# 기존: final_content += f'<img src="{uploaded_img_url}" ...'
# 개선: Featured Image로만 설정
```

**효과:**
- ✅ 대표 이미지 1개만 표시 (중복 제거)
- ✅ 페이지 로딩 속도 개선
- ✅ 깔끔한 레이아웃

**참고:** Featured Image는 WordPress 테마에서 자동으로 표시됩니다.

---

### 3. 과거 기사 순차 번역 (매일 10개씩)

**변경 내용:**
```python
# 오래된 순으로 정렬
all_articles.sort(key=lambda x: x['date'])

# 매일 10개만 처리
return all_articles[:DAILY_LIMIT]
```

**진행 방식:**
1. **1일차**: 가장 오래된 기사 10개 번역
2. **2일차**: 그 다음 오래된 기사 10개 번역
3. **3일차**: ...
4. **최종**: 모든 과거 기사 번역 완료

**예상 소요 시간:**
- drone.jp RSS에 약 100개 기사가 있다면: 10일
- 매일 새 기사 5개 추가된다면: 약 15-20일

**진행 상황 확인:**
```
실행 후 로그에 표시:
📊 남은 미번역 기사: XX개
```

---

### 4. drone.jp 유사 디자인

**변경 내용:**
```python
def add_drone_style(self, content):
    # CSS 스타일 추가
    - 폰트: Apple/Roboto 시스템 폰트
    - 색상: #333 (본문), #0066cc (링크)
    - 레이아웃: 최대 폭 800px, 중앙 정렬
    - 여백: 적절한 line-height, margin
```

**적용된 스타일:**
- ✅ 모던한 sans-serif 폰트
- ✅ 읽기 편한 줄 간격 (1.8)
- ✅ 드론 산업 느낌의 파란색 링크
- ✅ 블록 인용 스타일
- ✅ 이미지 자동 중앙 정렬

**추가 커스터마이징:**
WordPress 테마에서 추가로:
- 헤더/푸터 색상
- 사이드바 레이아웃
- 카테고리 디자인

---

## 🚀 사용 방법

### GitHub 저장소 업데이트

1. 기존 `translate_and_post.py` 파일 삭제
2. 새 파일 업로드
3. Commit & Push

### Actions 실행

1. GitHub → Actions
2. "Run workflow" 클릭
3. 10개 기사 번역 시작

### 매일 자동 실행

- 기존 스케줄 그대로 (매일 오전 9시)
- 매일 10개씩 자동으로 과거 기사 번역

---

## 📊 모니터링

### 진행 상황 확인

Actions 로그에서:
```
✅ 미번역 기사: 87개 (오래된 것부터 10개 처리)
...
🏁 완료: 10/10개 게시
📊 남은 미번역 기사: 77개
```

### 전체 번역 완료 시점 예상

```
남은 기사 / 10 = 예상 일수
예: 87개 / 10 = 약 9일
```

---

## 🎨 디자인 추가 개선 (선택사항)

### WordPress 테마 커스터마이징

**외모 → 사용자 정의 CSS에 추가:**

```css
/* drone.jp 스타일 */
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #333;
}

.site-header {
    background: #2c3e50;
    border-bottom: 3px solid #0066cc;
}

.entry-title a {
    color: #2c3e50;
}

.entry-meta {
    color: #777;
    font-size: 14px;
}

/* Featured Image 스타일 */
.post-thumbnail img {
    width: 100%;
    height: auto;
    object-fit: cover;
}
```

---

## ⚙️ 설정 변경

### 매일 처리 개수 변경

`translate_and_post.py` 파일:
```python
DAILY_LIMIT = 10  # 10 → 20으로 변경 (더 빠르게)
```

### 이미지를 본문에도 표시하고 싶다면

```python
# process_article() 함수에서:
if uploaded_img_url:
    final_content = f'<img src="{uploaded_img_url}" style="width:100%; margin-bottom:30px;">' + final_content
```

---

## 🐛 문제 해결

### "게시 실패: 403 Forbidden"
- WordPress Application Password 재생성
- GitHub Secrets 재확인

### "남은 미번역 기사: 0개"
- 모든 기사 번역 완료!
- 이제 새 기사만 자동 번역됨

### "이미지가 2개 보여요"
- WordPress 테마 설정 확인
- Featured Image 자동 표시 여부 확인
- 테마에서 이미 표시 중이면 코드에서 제거됨

---

## 📝 다음 단계

1. ✅ 파일 업로드
2. ✅ Actions 실행
3. ✅ https://grv.co.kr/wp 확인
4. ⏳ 매일 10개씩 과거 기사 자동 번역
5. 🎨 (선택) WordPress 테마 추가 커스터마이징
