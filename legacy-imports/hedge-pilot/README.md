# 김치 프리미엄 헤징 봇

한국 거래소와 해외 선물 거래소 간의 가격 차이(김치 프리미엄)를 활용한 자동 헤징 봇입니다.

## 📋 개요

이 봇은 한국 암호화폐 거래소(업비트, 빗썸)와 해외 선물 거래소(Gate.io) 간의 가격 차이를 실시간으로 모니터링하여, 프리미엄이 낮을 때 자동으로 헤징 포지션을 구축하고 프리미엄이 상승하면 단계별로 이익을 실현합니다.

### 주요 특징

- ✅ 실시간 김치 프리미엄 계산
- ✅ 자동 헤징 포지션 구축 (현물 매수 + 선물 숏)
- ✅ 단계별 이익 실현 시스템
- ✅ 타이머 기반 재진입 방지
- ✅ 다중 코인 동시 관리

## 🚀 시작하기

### 필수 요구사항

- Python 3.8 이상
- python-dotenv

### 설치

1. 저장소 클론
```bash
git clone https://github.com/yourusername/redflag-hedge.git
cd redflag-hedge
```

2. 필요한 패키지 설치
```bash
pip install ccxt python-dotenv
```

3. 환경 변수 설정
```bash
cp .env.example .env
```

`.env` 파일을 열어 각 거래소의 API 키와 시크릿을 입력하세요:

```env
# 한국 거래소
UPBIT_API_KEY=your_upbit_api_key
UPBIT_API_SECRET=your_upbit_api_secret

BITHUMB_API_KEY=your_bithumb_api_key
BITHUMB_API_SECRET=your_bithumb_api_secret

# 해외 선물 거래소
GATEIO_API_KEY=your_gateio_api_key
GATEIO_API_SECRET=your_gateio_api_secret
```

## 💻 사용법

봇 실행:
```bash
python main.py
```

실행 시 프롬프트:
1. 거래할 코인 심볼 입력 (예: `BTC,ETH,XRP`)
2. 한국 거래소 선택 (1: Upbit, 2: Bithumb)
3. 선물 거래소는 Gate.io로 자동 설정

## ⚙️ 설정

`src/config/settings.py`에서 다음 설정을 조정할 수 있습니다:

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `MAX_POSITION_USD` | $1,500 | 심볼당 최대 포지션 크기 |
| `POSITION_INCREMENT_USD` | $100 | 포지션 증가 단위 |
| `BUILD_POSITION_PREMIUM` | 0.0% | 포지션 구축 시작 프리미엄 |
| `STAGE_TIMER_MINUTES` | 30분 | 각 단계별 대기 시간 |
| `MAIN_LOOP_INTERVAL` | 60초 | 메인 루프 실행 간격 |

### 이익 실현 단계

| 프리미엄 | 청산 비율 |
|----------|-----------|
| 5% | 5% |
| 10% | 10% |
| 30% | 30% |
| 50% | 50% |
| 100% | 100% |

## 📁 프로젝트 구조

```
redflag-hedge/
│
├── main.py                 # 메인 실행 파일
├── .env.example           # 환경 변수 예시
│
└── src/
    ├── config/            # 설정 관리
    │   └── settings.py    # 봇 설정
    │
    ├── core/              # 핵심 로직
    │   ├── hedge_bot.py   # 헤징 봇 메인 클래스
    │   ├── premium_calculator.py  # 김치 프리미엄 계산
    │   └── order_executor.py      # 주문 실행
    │
    ├── exchanges/         # 거래소 API 래퍼
    │   ├── upbit.py      # 업비트 거래소
    │   ├── bithumb.py    # 빗썸 거래소
    │   └── gateio.py     # Gate.io 거래소
    │
    ├── managers/          # 관리 모듈
    │   ├── position_manager.py  # 포지션 관리
    │   └── timer_manager.py     # 타이머 관리
    │
    └── utils/             # 유틸리티
        └── logger.py      # 로깅 설정
```

## 🔧 핵심 기능 설명

### 김치 프리미엄 계산

```
프리미엄 = (한국_거래소_가격 / 해외_거래소_가격 - 1) × 100
```

- 한국 거래소 가격: 매수(ask) 가격 사용
- 해외 거래소 가격: 매도(bid) 가격 사용 (숏 진입 시)
- USDT/KRW 환율을 통해 정확한 USD 가격 변환

### 헤징 포지션 구축

1. 프리미엄이 0% 이하일 때 자동 진입
2. 한국 거래소에서 현물 매수 + Gate.io에서 동일 수량 선물 숏
3. 최소 주문 크기 $10 이상만 실행
4. 최대 포지션 $1,500까지 $100씩 점진적 구축

### 이익 실현 메커니즘

1. 프리미엄이 설정된 단계에 도달하면 해당 비율만큼 포지션 청산
2. 각 단계별 30분 타이머로 과도한 매매 방지
3. 100% 프리미엄 도달 시 전체 포지션 자동 청산

## ⚠️ 주의사항

- **API 키 관리**: API 키는 절대 공개하지 마세요
- **거래 권한**: API 키에 거래 권한이 있는지 확인하세요
- **수수료 고려**: 거래소별 수수료를 계산에 포함시키세요
- **최소 주문**: 각 거래소의 최소 주문 금액을 확인하세요
- **리스크 관리**: 실제 자금으로 운영 전 충분한 테스트를 진행하세요

## 📊 로그 확인

봇은 실행 중 다음 정보를 로그로 출력합니다:

- 각 코인의 실시간 프리미엄
- 포지션 구축/청산 내역
- 오류 및 경고 메시지

로그 파일: `redflag_hedge.log`

## 🤝 기여하기

버그 리포트, 기능 제안, 풀 리퀘스트를 환영합니다!

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## ⚡ 성능 및 안전 기능

- **동시 주문 실행**: ThreadPoolExecutor를 사용한 현물/선물 동시 주문
- **부분 실행 복구**: 한쪽 주문만 체결된 경우 자동 복구
- **중복 주문 방지**: 진행 중인 주문 추적으로 중복 방지
- **실패 관리**: 3회 실패 시 자동으로 해당 심볼 건너뛰기
- **안전한 선물 청산**: `reduce_only` 플래그로 의도치 않은 롱 포지션 방지

## 💡 팁

1. **프리미엄 모니터링**: 일반적으로 한국 시장 개장 시간에 프리미엄 변동이 큽니다
2. **코인 선택**: 거래량이 많고 양 거래소에 모두 상장된 코인을 선택하세요
3. **포지션 크기**: 초기에는 작은 금액으로 시작하여 시스템을 테스트하세요
4. **Gate.io 계약**: Gate.io는 소수점 계약을 지원하므로 정확한 헤징이 가능합니다