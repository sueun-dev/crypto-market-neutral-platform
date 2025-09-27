# Multi-Exchange Delta Neutral Hedge Bot

해외 거래소간 현물/선물 스프레드를 활용한 델타 중립 헤지 봇 (Gate.io, Bybit, OKX)

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

# 가상환경 생성 및 패키지 설치
uv venv
uv pip install ccxt python-dotenv requests
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

### 실시간 가격 테스트 (거래 없음)

```bash
# 방법 1: 직접 실행
source .venv/bin/activate
python tests/test_prices.py

# 방법 2: 다른 테스트
python tests/test_manual.py
```

### 실제 헤지 봇 실행

```bash
# 방법 1: 직접 실행
source .venv/bin/activate
python main.py

# 방법 2: 스크립트 사용
./run.sh
```

프로그램 실행 시:
1. 모드 선택 (자동/수동)
2. 코인 심볼 입력
3. 펀딩비 확인 및 진행 여부 결정
4. 자동 모니터링 및 거래 실행

## 설정 변경

`config.py`에서 조정 가능:

```python
ENTRY_AMOUNT = 20.0              # 회당 진입 금액 (USDT)
MAX_ENTRIES = 40                 # 최대 진입 횟수
PRICE_DIFF_THRESHOLD = 0.0021    # 진입 스프레드 (0.21%)
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