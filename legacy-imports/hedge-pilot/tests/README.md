# 레드플래그 헤지 봇 테스트

이 디렉토리에는 레드플래그 헤지 봇의 테스트 코드가 포함되어 있습니다.

## 📁 테스트 구조

```
tests/
├── unit/                  # 단위 테스트
│   └── (개별 함수 테스트)
│
├── integration/           # 통합 테스트
│   ├── test_integration_hedge.py    # 헤지 통합 테스트
│   ├── test_perfect_hedge.py        # 완벽한 헤지 테스트
│   ├── test_ip_hedge_comprehensive.py # IP 헤지 종합 테스트
│   ├── test_balance_comprehensive.py  # 균형 종합 테스트
│   ├── test_gno_trade.py            # GNO 거래 테스트
│   ├── test_xrp_trade.py            # XRP 거래 테스트
│   └── test_simple_gno.py           # 간단한 GNO 테스트
│
├── performance/           # 성능 테스트
│   ├── test_premium_performance.py  # 프리미엄 성능 테스트
│   └── test_real_performance.py     # 실제 성능 테스트
│
├── exchanges/             # 거래소별 테스트
│   ├── test_bithumb.py              # 빗썸 거래소 테스트
│   ├── test_live_bithumb.py         # 빗썸 라이브 테스트
│   ├── test_upbit_doge.py           # 업비트 DOGE 테스트
│   ├── test_gateio_futures.py       # Gate.io 선물 테스트
│   ├── test_gateio_auto.py          # Gate.io 자동 테스트
│   └── test_gateio_decimal.py       # Gate.io 소수점 테스트
│
├── core/                  # 핵심 기능 테스트
│   ├── test_bidask_logic.py         # Bid/Ask 로직 테스트
│   ├── test_comprehensive_bidask.py # 종합 Bid/Ask 테스트
│   └── test_position_balancer.py    # 포지션 밸런서 테스트
│
├── utilities/             # 유틸리티 및 헬퍼
│   ├── check_balance.py             # 잔고 확인 유틸리티
│   ├── check_krw.py                 # KRW 확인 유틸리티
│   └── test_position_check.py       # 포지션 체크 유틸리티
│
├── reports/               # 테스트 리포트
│   └── test_report_position_balancer.md
│
├── run_tests.py           # 테스트 실행 스크립트
└── TEST_DOCUMENTATION.md  # 완벽한 테스트 문서
```

## 🚀 빠른 시작

### 1. 환경 설정
```bash
# API 키 설정 (.env 파일)
BITHUMB_API_KEY=your_api_key
BITHUMB_API_SECRET=your_api_secret
GATEIO_API_KEY=your_api_key
GATEIO_API_SECRET=your_api_secret
UPBIT_ACCESS_KEY=your_access_key
UPBIT_SECRET_KEY=your_secret_key

# 패키지 설치
pip install -r requirements.txt
```

### 2. 테스트 실행

#### 전체 테스트 실행
```bash
python tests/run_tests.py
```

#### 카테고리별 실행
```bash
# 단위 테스트
python -m pytest tests/unit/ -v

# 통합 테스트
python -m pytest tests/integration/ -v

# 성능 테스트
python -m pytest tests/performance/ -v

# 거래소 테스트
python -m pytest tests/exchanges/ -v

# 핵심 기능 테스트
python -m pytest tests/core/ -v
```

#### 특정 테스트 실행
```bash
# 완벽한 헤지 테스트
python tests/integration/test_perfect_hedge.py

# 포지션 균형 체크
python tests/utilities/test_position_check.py

# 프리미엄 성능 테스트
python tests/performance/test_premium_performance.py
```

## 📊 주요 테스트 시나리오

### 1. 핵심 기능 테스트
- **Bid/Ask 로직**: 정확한 가격 계산 및 프리미엄 산출
- **포지션 밸런서**: 현물과 선물 간 균형 유지
- **헤지 실행**: Gate.io 정수 계약에 맞춘 완벽한 헤지

### 2. 통합 테스트
- **완벽한 헤지**: $50 목표로 정확한 헤지 포지션 구축
- **IP 헤지 종합**: IP 코인으로 전체 시나리오 테스트
- **균형 종합**: 불균형 생성 및 자동 리밸런싱

### 3. 성능 테스트
- **프리미엄 계산 성능**: 실시간 프리미엄 계산 속도
- **실제 성능**: 24시간 연속 운영 시뮬레이션

### 4. 거래소별 테스트
- **빗썸**: 시장가 주문, KRW 금액 기반 매수
- **업비트**: DOGE 거래, 수량 기반 주문
- **Gate.io**: 정수 계약, reduce_only 파라미터

## ⚠️ 주의사항

### 실제 거래 테스트
1. **실제 자금 사용**: 일부 테스트는 실제 거래를 실행합니다
2. **최소 잔고 필요**: 
   - 빗썸: 25,000 KRW
   - Gate.io: 50 USDT
3. **거래 수수료 발생**: 실제 거래 시 수수료가 차감됩니다
4. **시장 리스크**: 시장 상황에 따라 손실 가능

### 안전한 테스트
```bash
# 읽기 전용 테스트 (안전)
python tests/utilities/check_balance.py
python tests/utilities/check_krw.py

# 시뮬레이션 테스트
python tests/core/test_bidask_logic.py
```

## 📈 테스트 커버리지

### 현재 커버리지
- **HedgeBot**: 90% (6/7 메서드)
- **OrderExecutor**: 95% (7/7 메서드)
- **PositionBalancer**: 100% (3/3 메서드)
- **PremiumCalculator**: 100% (2/2 메서드)
- **Exchange APIs**: 85% (주요 기능)

### 목표
- 전체 커버리지: >90%
- 핵심 기능: 100%
- 통합 테스트: >80%

## 🔧 문제 해결

### API 키 오류
```
❌ API_KEY와 API_SECRET이 설정되어있지 않습니다
```
→ `.env` 파일에 올바른 API 키 설정

### 잔고 부족
```
❌ 충분한 잔고가 없습니다
```
→ 테스트용 자금 충전 또는 읽기 전용 테스트 실행

### Gate.io 정수 계약
```
❌ Gate.io는 정수 계약만 지원합니다
```
→ `test_gateio_decimal.py`로 정수 처리 확인

## 📝 테스트 작성 가이드

### 새 테스트 추가
1. 적절한 카테고리 폴더 선택
2. `test_` 접두사로 파일 생성
3. unittest 또는 pytest 사용
4. 독립적이고 반복 가능한 테스트 작성

### 테스트 템플릿
```python
import unittest
from src.core.hedge_bot import HedgeBot

class TestNewFeature(unittest.TestCase):
    def setUp(self):
        """테스트 초기화"""
        self.bot = HedgeBot(mock_korean, mock_futures)
    
    def test_feature(self):
        """기능 테스트"""
        result = self.bot.new_feature()
        self.assertEqual(result, expected)
    
    def tearDown(self):
        """정리 작업"""
        pass

if __name__ == "__main__":
    unittest.main()
```

## 📚 참고 문서

- [TEST_DOCUMENTATION.md](TEST_DOCUMENTATION.md) - 완벽한 테스트 가이드
- [포지션 밸런서 리포트](reports/test_report_position_balancer.md)
- [메인 README](../README.md)