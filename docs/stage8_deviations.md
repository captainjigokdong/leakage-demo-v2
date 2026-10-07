# 8단계: 계획과 다르게 한 것

계획 `docs/stage8_plan.md`(학습 전 커밋 `2408674`)와 실제 실행이 다른 점. 결과 숫자에는 영향이 없다.

## 1. tpot 설치 방법

계획 5절은 `SETUPTOOLS_USE_DISTUTILS=stdlib pip install tpot==1.1.0 matplotlib`였다. 이 환경(Python 3.13.16)에서는 다음 이유로 실패했다.
- Python 3.12부터 표준 라이브러리에 distutils가 없어, 이 환경 변수를 쓰면 setuptools가 빌드에 쓰이지 못한다.
- Debian의 setuptools 68.1.2는 `stopit`·`func-timeout` 빌드에서 `install_layout` 오류가 난다.
- setuptools 81 이상에는 `pkg_resources`가 없어, `stopit`을 불러올 때 오류가 난다.

실제로 설치한 방법: `pip install "setuptools<81"` → `pip install --no-build-isolation stopit func-timeout` → `pip install tpot==1.1.0 matplotlib`. setuptools 80.10.2는 `requirements-lock.txt`에 없는 패키지다. 설치 뒤 `requirements-lock.txt`의 24개 패키지 버전 변화는 0이고, 시험은 626 / 8 / 0이었다. 기록 `requirements-stage8-lock.txt`.

## 2. 첫 실행 오류와 재실행

첫 실행(코드 `c4cd959`)은 보조 데이터 안 B의 첫 설계, 첫 시드에서 오류로 멈췄다. v1 코드가 v2 `leakcheck.splitting`에 없는 함수(`effective_key_level`)를 불렀다.

AUROC를 계산하기 전에 멈췄다는 근거:
- 오류 기록 `results/stage8/first_run_error.log`. 실행을 감싼 셸의 출력이다. 실행 로그 전체는 재실행 때 같은 경로에 덮어써져 남아 있지 않다.
- 오류가 난 줄은 `c4cd959`의 `experiment/leakage_effect.py` 284행이다. AUROC를 처음 계산하는 줄은 292행(`lk.auroc`)이고, `run_one`에서 284행이 먼저 실행된다.
- 실행 결과 줄(`{"type": ...}` 형식)은 0줄이었다. 이 줄은 실행이 끝날 때마다 하나씩 출력된다. 이 수는 세션에서 센 값이고, 로그 전체가 남아 있지 않아 저장소 파일로는 다시 확인할 수 없다.
- 결과 파일은 묶음이 모두 끝난 뒤 한 번에 쓴다(402행 `write_text`). 그래서 `results/stage8/`에는 아무 파일도 생기지 않았다.

고친 것은 함수 호출 두 곳뿐이다(`0ffc604`: `effective_key_level` → `key_level`, `group_values`에 넘기는 인자). 조건·시드·특징·설정은 그대로 두고 처음부터 다시 돌렸다.

## 3. 가짜 데이터로 TPOT 점검

재실행 전에 TPOT 경로가 넘긴 가족 단위 조각을 실제로 쓰는지 한 번 확인했다. 무작위로 만든 가짜 데이터(300행, 5열, 그룹 100개)를 썼고, 실제 데이터와 결정 잠금은 쓰지 않았다. 결과: 걸린 시간 103초, 조각 분할 호출 60회, 넘긴 조각 객체 그대로 사용, 조각 사이 걸친 그룹 0. 이 결과는 저장하지 않았다.

## 4. 그림 범례 이동

결과 그림을 처음 만든 뒤 범례가 "all" 행의 점을 가려, 범례를 그림 아래로 옮겼다. "참조 대비"를 뜻하는 속 빈 점도 범례에 더했다(`experiment/stage8/report.py`). 수치와 점의 위치는 바꾸지 않았다.

## 5. TPOT 실행 횟수

계획을 승인받기 전 대화에서는 TPOT를 6회(본 데이터 4회, 보조 데이터 2회)로 적었다. 이후 보조 데이터를 안 A와 안 B 둘 다 돌리기로 하면서, 커밋한 계획 문서(4절)에 8회로 적었다. 그대로 8회 돌렸다. 커밋한 계획과 다른 점은 없다.
