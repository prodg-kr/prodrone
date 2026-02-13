# 일본 드론 뉴스 자동 번역 및 워드프레스 게시 시스템

drone.jp의 최신 뉴스를 자동으로 한국어로 번역하여 워드프레스 블로그에 게시하는 시스템입니다.

## 🎯 기능

- ✅ 매일 오전 9시 자동 실행
- ✅ drone.jp RSS 피드 모니터링
- ✅ Google Translate로 고품질 한국어 번역
- ✅ 원본 이미지 자동 다운로드 및 업로드
- ✅ 중복 게시 방지
- ✅ 완전 무료 (GitHub Actions 사용)

## 📋 사전 준비

### 1. 워드프레스 Application Password 생성

1. https://grv.co.kr/wp/wp-admin/ 로그인
2. 좌측 메뉴 → **사용자** → **프로필**
3. 아래로 스크롤 → **애플리케이션 비밀번호** 섹션
4. 새 애플리케이션 비밀번호 이름: `GitHub Actions`
5. **새 애플리케이션 비밀번호 추가** 클릭
6. 생성된 비밀번호 복사 (공백 포함, 예: `xxxx xxxx xxxx xxxx xxxx xxxx`)

### 2. GitHub 계정 준비

- GitHub 계정이 없다면: https://github.com/join 에서 가입

## 🚀 설치 방법

### Step 1: GitHub 저장소 생성

1. GitHub 로그인
2. https://github.com/new 접속
3. Repository name: `wordpress-news-automation` (원하는 이름)
4. Private 선택 (권장)
5. **Create repository** 클릭

### Step 2: 코드 업로드

#### 방법 A: GitHub 웹에서 직접 업로드

1. 생성된 저장소에서 **Add file** → **Upload files** 클릭
2. 다음 파일들을 드래그 앤 드롭:
   - `translate_and_post.py`
   - `requirements.txt`
3. **Commit changes** 클릭

4. `.github/workflows` 폴더 생성:
   - 저장소 메인 페이지에서 **Add file** → **Create new file**
   - 파일 이름에 `.github/workflows/auto-translate.yml` 입력
   - `auto-translate.yml` 파일 내용 붙여넣기
   - **Commit changes** 클릭

#### 방법 B: Git CLI 사용 (권장)

```bash
# 이 프로젝트 파일들을 다운로드한 폴더에서
cd wordpress-news-automation

# Git 초기화
git init
git add .
git commit -m "Initial commit: 자동 번역 시스템"

# GitHub 저장소와 연결 (본인의 저장소 URL로 변경)
git remote add origin https://github.com/YOUR_USERNAME/wordpress-news-automation.git

# 업로드
git branch -M main
git push -u origin main
```

### Step 3: GitHub Secrets 설정

1. GitHub 저장소 페이지에서 **Settings** 탭 클릭
2. 좌측 메뉴 → **Secrets and variables** → **Actions**
3. **New repository secret** 클릭

**첫 번째 Secret:**
- Name: `WP_USER`
- Value: 워드프레스 관리자 아이디 (예: `admin`)
- **Add secret** 클릭

**두 번째 Secret:**
- Name: `WP_APP_PASSWORD`
- Value: Step 1에서 생성한 Application Password (공백 포함 전체)
- **Add secret** 클릭

### Step 4: GitHub Actions 활성화

1. 저장소에서 **Actions** 탭 클릭
2. 워크플로우가 보이면 활성화
3. **I understand my workflows, go ahead and enable them** 클릭

## ✅ 테스트 실행

수동으로 즉시 실행해보기:

1. **Actions** 탭 클릭
2. 좌측에서 "일본 드론 뉴스 자동 번역 및 게시" 클릭
3. **Run workflow** 버튼 클릭 (우측 상단)
4. **Run workflow** 다시 클릭

5-10분 후 https://grv.co.kr/wp 에서 새 게시물 확인!

## 📅 자동 실행 스케줄

- **기본 설정:** 매일 오전 9시 (한국 시간)
- **수정 방법:** `.github/workflows/auto-translate.yml` 파일의 cron 값 변경

```yaml
schedule:
  - cron: '0 0 * * *'  # 매일 오전 9시
  # cron: '0 */6 * * *'  # 6시간마다
  # cron: '0 0,12 * * *'  # 오전 9시, 오후 9시
```

## 🔧 설정 커스터마이징

### 게시할 기사 개수 변경

`translate_and_post.py` 파일에서:

```python
for article in articles[:5]:  # 하루 최대 5개
```

숫자를 원하는 만큼 변경

### RSS 피드 추가

다른 일본 뉴스 사이트도 추가하려면:

```python
DRONE_JP_RSS = "https://drone.jp/feed"
OTHER_RSS = "https://example.jp/feed"  # 추가
```

## 📊 모니터링

### 실행 로그 확인

1. GitHub 저장소 → **Actions** 탭
2. 최근 워크플로우 실행 클릭
3. **translate-and-post** 작업 클릭
4. 각 단계별 로그 확인 가능

### 게시된 기사 확인

- 워드프레스 관리자: https://grv.co.kr/wp/wp-admin/edit.php
- 블로그 메인: https://grv.co.kr/wp

## ⚠️ 문제 해결

### "인증 실패" 오류

- GitHub Secrets에 `WP_USER`와 `WP_APP_PASSWORD`가 정확히 입력되었는지 확인
- Application Password를 공백 포함하여 정확히 복사했는지 확인

### "번역 실패" 오류

- Google Translate API 할당량 확인 (월 50만자)
- 네트워크 연결 문제일 수 있음 (자동 재시도됨)

### "새로운 기사가 없습니다"

- 정상입니다! 24시간 내 새 기사가 없으면 이 메시지가 표시됩니다.
- drone.jp에 실제로 새 기사가 올라왔는지 확인

## 💡 추가 기능 아이디어

- [ ] 이메일 알림 추가
- [ ] 카테고리 자동 분류
- [ ] 여러 일본 뉴스 사이트 지원
- [ ] 번역 품질 개선 (DeepL로 업그레이드)
- [ ] 태그 자동 생성

## 📝 라이선스

MIT License - 자유롭게 사용하세요!

## 🙋‍♂️ 지원

문제가 있으면 GitHub Issues에 등록해주세요.
