# 🚀 5분 만에 시작하기

## 1️⃣ 워드프레스 Application Password 생성 (2분)

1. https://grv.co.kr/wp/wp-admin/ 로그인
2. 좌측 **사용자** → **프로필** 클릭
3. 아래로 스크롤 → **애플리케이션 비밀번호** 찾기
4. 이름: `GitHub Actions` 입력
5. **새 애플리케이션 비밀번호 추가** 클릭
6. 📋 생성된 비밀번호 복사 (예: `AbCd 1234 EfGh 5678 IjKl 9012`)

## 2️⃣ GitHub 저장소 생성 (1분)

1. https://github.com/new 접속
2. Repository name: `wp-news-auto` (아무 이름이나 가능)
3. **Private** 선택
4. **Create repository** 클릭

## 3️⃣ 코드 업로드 (1분)

### 옵션 A: 파일 드래그 앤 드롭 (쉬움)

1. 저장소에서 **uploading an existing file** 클릭
2. 다음 파일들을 드래그:
   - `translate_and_post.py`
   - `requirements.txt`
   - `.gitignore`
   - `README.md`
3. **Commit changes** 클릭

4. 다시 **Add file** → **Create new file**
5. 파일명: `.github/workflows/auto-translate.yml`
6. 내용 붙여넣기
7. **Commit** 클릭

### 옵션 B: Git CLI (빠름)

```bash
git clone https://github.com/YOUR_USERNAME/wp-news-auto.git
cd wp-news-auto

# 프로젝트 파일들 복사
# (translate_and_post.py, requirements.txt 등)

git add .
git commit -m "자동 번역 시스템"
git push
```

## 4️⃣ GitHub Secrets 설정 (1분)

1. 저장소 → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭

**첫 번째:**
- Name: `WP_USER`
- Value: 워드프레스 아이디 (예: `admin`)

**두 번째:**
- Name: `WP_APP_PASSWORD`  
- Value: 1단계에서 복사한 비밀번호 (공백 포함!)

## 5️⃣ 테스트 실행! (30초)

1. 저장소 → **Actions** 탭
2. 워크플로우 활성화 (필요시)
3. **Run workflow** → **Run workflow** 클릭
4. 5분 대기 ⏱️
5. https://grv.co.kr/wp 확인! 🎉

---

## ✅ 완료!

이제 매일 오전 9시마다 자동으로 일본 드론 뉴스가 번역되어 게시됩니다.

## 📞 문제 발생시

1. **Actions** 탭에서 로그 확인
2. README.md의 "문제 해결" 섹션 참고
3. GitHub Issues에 질문 등록
