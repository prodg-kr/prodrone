# 🔄 기존 게시물 삭제 후 재게시 가이드

## 문제 상황

WordPress에서 게시물을 삭제했는데, 다시 실행해도 "이미 게시됨"으로 인식되어 재게시 안 됨.

**원인:** GitHub Actions 캐시에 `posted_articles.json` 파일이 저장되어 있음

---

## ✅ 해결 방법 (3가지)

### 방법 1: GitHub Actions 캐시 삭제 ⭐ 추천

**단계:**
1. GitHub 저장소 접속
2. **Actions** 탭 클릭
3. 좌측 메뉴 → **Management** → **Caches** 클릭
4. `posted-articles-` 로 시작하는 캐시 찾기
5. 오른쪽 🗑️ 아이콘 클릭하여 삭제
6. **Actions** → **Run workflow** 다시 실행

**효과:**
- 깨끗하게 초기화
- 모든 기사를 다시 번역 가능

---

### 방법 2: 환경 변수로 강제 모드 활성화 (임시)

**단계:**
1. GitHub 저장소 → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭
3. 입력:
   - Name: `FORCE_UPDATE`
   - Value: `true`
4. **Actions** → **Run workflow** 실행
5. 완료 후 `FORCE_UPDATE` Secret 삭제 (또는 값을 `false`로 변경)

**효과:**
- 한 번만 모든 기사 재번역
- Secret 삭제 후 다시 정상 모드로

---

### 방법 3: 코드에서 직접 변경 (빠른 테스트용)

**단계:**
1. `translate_and_post.py` 파일 편집
2. 상단 설정 부분 수정:
   ```python
   # 기존
   FORCE_UPDATE = os.environ.get("FORCE_UPDATE", "false").lower() == "true"
   
   # 임시 변경
   FORCE_UPDATE = True  # ← 이렇게 변경
   ```
3. GitHub 커밋
4. Actions 실행
5. 완료 후 다시 `False`로 되돌리기

**주의:** 다시 `False`로 되돌리는 것 잊지 마세요!

---

## 📊 각 방법 비교

| 방법 | 난이도 | 추천도 | 용도 |
|------|--------|--------|------|
| 캐시 삭제 | 쉬움 | ⭐⭐⭐ | 완전 초기화 |
| 환경 변수 | 중간 | ⭐⭐ | 한 번만 재번역 |
| 코드 수정 | 쉬움 | ⭐ | 긴급 테스트 |

---

## 🎯 추천 워크플로우

### 시나리오 1: "이미지 문제로 전체 재게시"

1. WordPress에서 기존 글 전체 삭제
2. GitHub Actions 캐시 삭제 (방법 1)
3. 새 코드로 "Run workflow" 실행
4. ✅ 모든 기사 새로 번역 및 게시

### 시나리오 2: "몇 개만 다시 올리고 싶음"

1. WordPress에서 특정 글만 삭제
2. `posted_articles.json` 캐시 삭제
3. 코드의 `DAILY_LIMIT` 조정:
   ```python
   DAILY_LIMIT = 5  # 5개만 처리
   ```
4. "Run workflow" 실행

### 시나리오 3: "급하게 테스트"

1. 코드에서 `FORCE_UPDATE = True` 설정
2. `DAILY_LIMIT = 1` 설정 (1개만 테스트)
3. "Run workflow" 실행
4. ✅ 완료 후 원복

---

## ⚠️ 주의사항

### 중복 게시 방지

- `FORCE_UPDATE = True` 상태에서 매일 자동 실행되면 계속 중복 게시됨
- 반드시 한 번 실행 후 `False`로 되돌리기!

### 권장 사용

```python
# 평소 (자동 실행)
FORCE_UPDATE = False  # 중복 게시 방지

# 재게시 필요할 때만 (수동 실행)
FORCE_UPDATE = True   # 임시로만 사용
```

---

## 💡 팁: 환경 변수 방식이 가장 안전

**이유:**
- 코드는 `False` 유지 (안전)
- 필요할 때만 Secret으로 `true` 설정
- 실행 후 Secret 삭제하면 자동으로 `False`

**설정:**
```python
# 코드는 이대로 유지
FORCE_UPDATE = os.environ.get("FORCE_UPDATE", "false").lower() == "true"
```

**사용:**
- 재게시 필요: Secret 추가 (`FORCE_UPDATE=true`)
- 완료 후: Secret 삭제
- 자동으로 `False` 모드로 복귀 ✅
