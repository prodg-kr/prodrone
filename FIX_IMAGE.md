# 이미지 파일명 문제 해결 (v3)

## 🐛 문제

이미지 URL이 깨져서 표시되지 않는 문제:
```
https://grv.co.kr/wp/wp-content/uploads/2026/02/20260210_tohzi_L1gKYYQf.jpg
```

**원인:**
- 원본 파일명에 한글이나 특수문자 포함
- URL 인코딩 문제
- 파일명이 너무 길거나 복잡함

## ✅ 해결

**안전한 파일명 생성 방식:**

```python
# 기존 (문제):
filename = os.path.basename(url)  # 원본 파일명 그대로 사용

# 개선 (해결):
filename = f"drone_{timestamp}_{hash}.jpg"
# 예: drone_1739456789_a1b2c3d4.jpg
```

**파일명 구성:**
- `drone_` : 고정 접두사
- `타임스탬프` : 고유성 보장
- `해시값` : URL 기반 8자리 해시
- 확장자 : .jpg, .png 등

**장점:**
- ✅ 한글/특수문자 없음
- ✅ 항상 유효한 파일명
- ✅ 중복 방지
- ✅ URL 인코딩 문제 없음

## 🚀 적용 방법

1. 새 `translate_and_post.py` 파일로 교체
2. GitHub에 커밋
3. Actions 실행
4. 이제 이미지가 정상 표시됨!

## 📊 확인

다음 실행부터는 이런 형식으로 저장됩니다:
```
/wp-content/uploads/2026/02/drone_1739456789_a1b2c3d4.jpg
```

깔끔하고 안전한 파일명! ✨
