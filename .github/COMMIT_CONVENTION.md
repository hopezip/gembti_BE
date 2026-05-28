# 커밋 메시지 컨벤션

## 형식

```
type(scope): 제목

본문 (선택)

이슈 (선택)
```

---

## type 목록

| type | 설명 | 예시 |
|------|------|------|
| `feat` | 새로운 기능 추가 | feat(auth): 이메일 로그인 구현 |
| `fix` | 버그 수정 | fix(recommend): 코사인 유사도 계산 오류 수정 |
| `refactor` | 기능 변경 없는 코드 개선 | refactor(survey): 설문 서비스 레이어 분리 |
| `test` | 테스트 코드 추가·수정 | test(auth): JWT 검증 단위 테스트 추가 |
| `docs` | 문서 수정 | docs: README 업데이트 |
| `chore` | 빌드·설정·패키지 변경 | chore: pyproject.toml 의존성 추가 |
| `style` | 포맷·공백 등 코드 스타일 | style: black 포맷 적용 |
| `perf` | 성능 개선 | perf(recommend): 추천 결과 Redis 캐싱 추가 |
| `db` | DB 모델·마이그레이션 변경 | db(auth): users 테이블 phone_number 컬럼 추가 |

---

## scope 목록

```
auth        회원/인증
steam       Steam 연동
survey      설문조사
stat        성향 분석
recommend   추천 엔진
game        게임 정보
chat        설문 챗봇
support     고객센터 챗봇
chat_common 챗봇 공통
core        핵심 설정
common      공통 유틸
infra       Docker, Nginx, CI/CD
```

---

## 작성 규칙

- 제목은 50자 이내
- 제목 끝에 마침표 없음
- 제목은 한글로 작성
- 본문은 무엇을, 왜 변경했는지 설명
- 이슈 번호는 `closes #번호` 형식

---

## 예시

```
feat(auth): 이메일 회원가입 API 구현

- 이메일 인증 코드 발송 (6자리, 5분 유효)
- bcrypt 비밀번호 해싱 적용
- Pydantic v2 입력값 검증

closes #12
```

```
fix(recommend): warning_list 분리 누락 수정

비선호 태그 충돌 게임이 일반 추천 목록에
포함되는 버그 수정

closes #34
```

```
db(auth): users 테이블 last_login_at 컬럼 추가

배포 담당자에게 알림 완료
alembic revision 생성 필요
```

```
chore: pyproject.toml fastapi-mail 의존성 추가
```
