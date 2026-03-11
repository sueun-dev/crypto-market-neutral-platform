# Crypto Market Neutral Platform

KRW 프리미엄과 해외 거래소간 현물/선물 스프레드를 활용하는 시장중립 자동화 플랫폼입니다. 기존 `overseas_exchange_hedge`를 기반으로 한국 진입 워크플로와 해외 자동 진입 워크플로를 통합했습니다.

## 핵심 기능

- **크로스 거래소 차익거래**: 가장 싼 현물 + 가장 비싼 선물 자동 매칭
- **펀딩비 체크**: 음수 펀딩비 회피로 비용 최소화
- **델타 중립**: 선물 체결량에 맞춘 정확한 현물 수량 조정
- **자동/수동 모드**: 전체 자동화 또는 특정 거래소 지정 가능

## 전략

### 콘탱고 캡처 전략 (Contango Capture Strategy)

콘탱고(Contango)는 선물 가격이 현물 가격보다 높은 상황을 의미합니다. 이 봇은 이러한 가격 차이를 포착하여 수익을 창출합니다.

#### 포지션 구축 과정
1. **기회 포착**: 선물 가격 > 현물 가격 (콘탱고) 상황 감지
2. **스프레드 계산**: `(선물가 - 현물가) / 현물가`가 임계값(0.21%) 초과 확인
3. **델타 중립 실행**:
   - 현물 매수 (Long): 가장 저렴한 거래소에서
   - 선물 매도 (Short): 가장 비싼 거래소에서 1x 레버리지로
4. **수익 확정**: 스프레드 수렴 시 포지션 청산으로 수익 실현

### 리스크 관리
- **델타 중립**: 현물과 선물 포지션을 동일 수량으로 유지
- **1x 레버리지**: 청산 리스크 최소화
- **분할 진입**: 여러 번에 걸쳐 포지션 구축
- **펀딩비 관리**: 음수 펀딩비 회피

## 활용 시나리오

### 한국 거래소 신규 상장 차익거래

이 시스템은 한국 거래소(빗썸, 업비트 등)에 새로운 코인이 상장될 때 발생하는 프리미엄을 활용하기 위해 설계되었습니다.

#### 전략적 포지셔닝
한국 거래소 상장 예정 코인이 해외 거래소에 이미 상장되어 있을 때:
1. **콘탱고 상황 포착**: 해외 거래소에서 선물이 현물보다 비싼 콘탱고 상황 또는 중립(0%) 상황에서 진입
2. **델타 중립 구축**: 현물 매수 + 선물 숏 포지션으로 가격 변동 리스크 완전 헤지
3. **프리미엄 실현**: 한국 거래소에서 입출금이 가능할때 현물을 이전하여 김치 프리미엄으로 추가 수익 실현


## 설치

### UV 설치 및 설정

```bash
# UV 설치 (아직 없다면)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 프로젝트 의존성 설치 (개발 도구 포함)
uv sync --dev
```

## 환경 설정

1. `.env` 파일 생성:
```bash
cp .env.example .env
```

2. API 키 입력:
```env
# GateIO
GATEIO_API_KEY=your_key
GATEIO_API_SECRET=your_secret

# Bybit
BYBIT_API_KEY=your_key
BYBIT_API_SECRET=your_secret

# OKX
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_API_PASSWORD=your_password
```

## 사용법

### Unified CLI (추천)

```bash
# 통합 메뉴 실행
uv run market-neutral
```

실행 중 생성되는 상태/캐시/로그는 기본적으로 `runtime/` 아래에 저장됩니다. (필요 시 `OEH_RUNTIME_DIR`로 위치 변경 가능)

### 흡수된 워크플로

```bash
# 한국 거래소 기준 진입
uv run market-neutral-korea-entry

# 해외 거래소 수동 진입
uv run market-neutral-overseas-entry-manual

# 해외 거래소 자동 진입
uv run market-neutral-overseas-entry-auto

# 한국 프리미엄 청산
uv run market-neutral-korea-exit

# 해외 포지션 청산
uv run market-neutral-overseas-unwind
```

기존 `hedge`, `hedge-exit`, `hedge-redflag` 명령도 호환성 때문에 유지합니다.

### 해외 헤지 진입

```bash
# 통합 메뉴에서 3(수동) 또는 5(자동) 선택
uv run market-neutral
```

#### 실행 옵션:
1. **모드 선택**
   - **자동 모드**: 모든 거래소에서 최적의 조합 자동 탐색
   - **수동 모드**: 특정 거래소 지정 (예: 현물 Bybit, 선물 Gate.io)

2. **코인 선택**
   - BTC, ETH, SOL 등 주요 코인
   - 신규 상장 예정 코인 (IP, USDC 등)

3. **실행 프로세스**
   - 펀딩비 확인 (음수 펀딩비 경고)
   - 실시간 스프레드 모니터링
   - 목표 스프레드 달성 시 자동 진입
   - 포지션 요약 및 빗썸 목표가 표시

#### 포지션 구축 예시:
```
📊 Best Opportunity:
  Buy:  BYBIT @ $8.41
  Sell: GATEIO @ $8.42
  Spread: 0.119%
  ✅ READY TO ENTER

🎯 Executing hedge...
✅ GATEIO Perp Short: 1.19 IP @ $8.42
✅ BYBIT Spot Buy: 1.19 IP for $10.00
```

### 김치 프리미엄 Exit

```bash
# 통합 Exit Manager 실행
uv run market-neutral-korea-exit
```

#### 주요 기능:
1. **실제 포지션 자동 감지**
   - 모든 거래소의 선물 숏 포지션 스캔
   - 빗썸/업비트 현물 잔고 확인

2. **스마트 주문 관리**
   - **주문 배치 김프**: 설정값 이상일 때 지정가 주문 생성
   - **체결 허용 김프**: 이 수준에서 주문 유지
   - **자동 취소**: 김프가 낮아지면 주문 자동 취소

3. **실시간 헤지 청산**
   - 한국 거래소 매도 체결 감지
   - 체결된 수량만큼 즉시 해외 선물 숏 청산
   - 델타 중립 유지

#### Exit 실행 예시:
```
📊 BITHUMB
  김프: 3.2% (vs GATEIO)
  📝 주문 배치 중...
    📝 주문: 10.3500 USDC @ ₩1,441
    📝 주문: 10.3500 USDC @ ₩1,442

  💰 체결: 5.0000 USDC @ ₩1,441
  🔄 선물 헤지 청산 중...
  ✅ GATEIO 숏 청산: 5.0000 USDC
```

#### 병렬 처리 최적화:
- 거래소 연결: 3배 빠른 초기화
- 김프 계산: 3개 API 동시 호출
- 실시간 모니터링: 5초 간격

### 추가 도구

```bash
# 전체 테스트/품질 게이트
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest

# 상태 파일 관리
rm -f runtime/state/exit_state.json  # Exit 상태 초기화
```

## 설정 변경

`src/overseas_exchange_hedge/config.py`에서 조정 가능:

```python
ENTRY_AMOUNT = 20.0              # 회당 진입 금액 (USDT)
MAX_ENTRIES = 40                 # 최대 진입 횟수
PRICE_DIFF_THRESHOLD = 0.0021    # 진입 스프레드 (0.21%) - 콘탱고
SLEEP_SEC = 10                   # 체크 주기
FUTURES_LEVERAGE = 1             # 선물 레버리지 (항상 1x)
```

## 주의사항

1. **API 권한**: 거래 권한이 있는 API 키 필요
2. **잔고 확인**: 충분한 USDT 잔고 필요
3. **선물 계좌**: 선물 계좌에 증거금 필요
4. **네트워크**: 안정적인 인터넷 연결 필수
5. **리스크 관리**: 실제 자금으로 운영 전 충분한 테스트

## 문제 해결

### UV 설치 문제
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 패키지 설치 문제
```bash
# 가상환경 재생성
rm -rf .venv
uv venv
uv pip install ccxt python-dotenv requests
```





bytbit deposit/withdraw status: https://www.bybit.com/x-api/v3/private/cht/asset-common/coin-status
