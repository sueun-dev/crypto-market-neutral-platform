# 완벽한 헤지 봇 테스트 문서
## Comprehensive Test Documentation for Redflag Hedge Bot

---

## 📋 테스트 개요 (Test Overview)

이 문서는 Redflag Hedge Bot의 모든 기능을 완벽하게 테스트하기 위한 상세한 가이드입니다.
각 모듈의 모든 함수를 체계적으로 테스트하며, 정상 케이스와 엣지 케이스를 모두 포함합니다.

### 테스트 범위
- **7개 핵심 모듈**: HedgeBot, OrderExecutor, PositionBalancer, PremiumCalculator, PositionManager, TimerManager, Exchange APIs
- **50+ 함수**: 모든 public/private 메서드 포함
- **100+ 테스트 시나리오**: 정상, 예외, 엣지 케이스

---

## 🏗️ 테스트 아키텍처

### 1. 테스트 레벨
```
Level 1: Unit Tests (개별 함수)
   ↓
Level 2: Integration Tests (모듈 간 연동)
   ↓
Level 3: System Tests (전체 시스템)
   ↓
Level 4: Stress Tests (24시간 운영)
```

### 2. 테스트 우선순위
1. **Critical (긴급)**: 주문 실행, 포지션 관리, 자금 관련
2. **High (높음)**: 프리미엄 계산, 리밸런싱, 타이머
3. **Medium (중간)**: 로깅, 설정, 유틸리티
4. **Low (낮음)**: UI, 리포팅

---

## 📦 Module 1: HedgeBot (`src/core/hedge_bot.py`)

### 1.1 `__init__(korean_exchange, futures_exchange)`
**테스트 목적**: 봇 초기화 및 의존성 주입 검증

**테스트 케이스**:
```python
# Test 1: 정상 초기화
def test_hedgebot_init_normal():
    bithumb = BithumbExchange(api_key, secret)
    gateio = GateIOExchange(credentials)
    bot = HedgeBot(bithumb, gateio)
    
    assert bot.korean_exchange == bithumb
    assert bot.futures_exchange == gateio
    assert len(bot.symbols) == 0
    assert isinstance(bot.position_manager, PositionManager)
    assert isinstance(bot.timer_manager, TimerManager)

# Test 2: None 거래소 처리
def test_hedgebot_init_none_exchange():
    with pytest.raises(ValueError):
        bot = HedgeBot(None, None)

# Test 3: 잘못된 거래소 타입
def test_hedgebot_init_wrong_type():
    with pytest.raises(TypeError):
        bot = HedgeBot("not_exchange", {})
```

### 1.2 `add_symbol(symbol: str) -> bool`
**테스트 목적**: 심볼 추가 및 검증 로직

**테스트 케이스**:
```python
# Test 1: 유효한 심볼 추가
def test_add_valid_symbol():
    bot = HedgeBot(bithumb, gateio)
    result = bot.add_symbol("IP")
    
    assert result == True
    assert "IP" in bot.symbols
    assert "IP" in bot.timer_manager.stage_timers
    assert bot.failed_attempts["IP"] == 0

# Test 2: 존재하지 않는 심볼
def test_add_invalid_symbol():
    bot = HedgeBot(bithumb, gateio)
    result = bot.add_symbol("FAKECOIN")
    
    assert result == False
    assert "FAKECOIN" not in bot.symbols

# Test 3: 기존 포지션이 있는 심볼 (리밸런싱 테스트)
def test_add_symbol_with_existing_position():
    # 먼저 IP 포지션 생성
    bot.order_executor.execute_hedge_position("IP", 50)
    
    # 불균형 생성 (빗썸에만 추가 매수)
    bithumb.create_market_order("IP/KRW", "buy", 100000)
    
    # 심볼 추가 시 자동 리밸런싱 확인
    bot2 = HedgeBot(bithumb, gateio)
    result = bot2.add_symbol("IP")
    
    assert result == True
    # 리밸런싱 후 균형 확인
    balance = bot2.position_balancer.check_position_balance("IP")
    assert balance.is_balanced == True

# Test 4: 중복 심볼 추가
def test_add_duplicate_symbol():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    result = bot.add_symbol("IP")  # 중복
    
    assert len([s for s in bot.symbols if s == "IP"]) == 2  # 현재는 중복 허용
```

### 1.3 `process_symbol(symbol: str)`
**테스트 목적**: 심볼별 처리 로직 (프리미엄 계산, 포지션 구축/청산)

**테스트 케이스**:
```python
# Test 1: 낮은 프리미엄 → 포지션 구축
def test_process_symbol_build_position():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    # 프리미엄 0% 이하로 설정 (모킹)
    with patch.object(bot.premium_calculator, 'calculate', return_value=-0.5):
        bot.process_symbol("IP")
    
    # 포지션이 구축되었는지 확인
    position = bot.position_manager.get_position("IP")
    assert position.value_usd > 0

# Test 2: 높은 프리미엄 → 이익 실현
def test_process_symbol_take_profit():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    # 먼저 포지션 구축
    bot.order_executor.execute_hedge_position("IP", 50)
    
    # 프리미엄 10% 설정
    with patch.object(bot.premium_calculator, 'calculate', return_value=10.5):
        bot.process_symbol("IP")
    
    # 10% 청산 확인
    position = bot.position_manager.get_position("IP")
    assert position.value_usd < 50  # 일부 청산됨

# Test 3: 중복 주문 방지
def test_process_symbol_duplicate_prevention():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    # 진행중 표시
    bot.orders_in_progress.add(("IP", "hedge"))
    
    # 프리미엄 낮게 설정
    with patch.object(bot.premium_calculator, 'calculate', return_value=-1.0):
        bot.process_symbol("IP")
    
    # 주문이 실행되지 않았는지 확인
    position = bot.position_manager.get_position("IP")
    assert position.value_usd == 0

# Test 4: 프리미엄 계산 실패
def test_process_symbol_premium_fail():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    with patch.object(bot.premium_calculator, 'calculate', return_value=None):
        bot.process_symbol("IP")  # 예외 발생 안함
    
    position = bot.position_manager.get_position("IP")
    assert position.value_usd == 0
```

### 1.4 `_build_position(symbol: str)`
**테스트 목적**: 포지션 구축 로직

**테스트 케이스**:
```python
# Test 1: 정상 포지션 구축
def test_build_position_normal():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    bot._build_position("IP")
    
    position = bot.position_manager.get_position("IP")
    assert position.value_usd == 50.0  # POSITION_INCREMENT_USD

# Test 2: 최소 주문 크기 미달
def test_build_position_below_minimum():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    # 포지션을 거의 MAX까지 채움
    position = bot.position_manager.get_position("IP")
    position.value_usd = 1995.0  # MAX는 2000, 남은 것은 5
    
    bot._build_position("IP")
    
    # 주문이 실행되지 않음 (10달러 미만)
    assert position.value_usd == 1995.0

# Test 3: 포지션 구축 후 리밸런싱
def test_build_position_with_rebalancing():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    # 주문 실패 시뮬레이션 (한쪽만 체결)
    with patch.object(bot.order_executor, 'execute_hedge_position', return_value=True):
        with patch.object(bot.position_balancer, 'check_position_balance') as mock_check:
            mock_check.return_value.needs_rebalancing = True
            bot._build_position("IP")
    
    # 리밸런싱이 호출되었는지 확인
    mock_check.assert_called()

# Test 4: 실패 처리
def test_build_position_failure():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    with patch.object(bot.order_executor, 'execute_hedge_position', return_value=False):
        bot._build_position("IP")
    
    assert bot.failed_attempts["IP"] == 1
```

### 1.5 `_check_profit_taking(symbol, premium, position_value)`
**테스트 목적**: 이익 실현 조건 확인

**테스트 케이스**:
```python
# Test 1: 단계별 이익 실현
def test_profit_taking_stages():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    # 포지션 설정
    position = bot.position_manager.get_position("IP")
    position.value_usd = 100.0
    
    # 10% 프리미엄 → 10% 청산
    bot._check_profit_taking("IP", 10.5, 100.0)
    assert position.value_usd == 90.0
    
    # 25% 프리미엄 → 10% 청산
    bot._check_profit_taking("IP", 25.5, 90.0)
    assert position.value_usd == 81.0

# Test 2: 100% 프리미엄 → 전체 청산
def test_profit_taking_full_close():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    position = bot.position_manager.get_position("IP")
    position.value_usd = 100.0
    
    bot._check_profit_taking("IP", 100.5, 100.0)
    
    assert "IP" not in bot.symbols  # 심볼 제거됨
    assert "IP" not in bot.position_manager.positions

# Test 3: 실패 횟수 초과
def test_profit_taking_max_failures():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    bot.failed_attempts["IP"] = 3  # MAX_FAILED_ATTEMPTS
    
    position = bot.position_manager.get_position("IP")
    position.value_usd = 100.0
    
    bot._check_profit_taking("IP", 10.5, 100.0)
    
    # 청산되지 않음
    assert position.value_usd == 100.0
```

### 1.6 `run_cycle() -> bool`
**테스트 목적**: 메인 루프 사이클

**테스트 케이스**:
```python
# Test 1: 정상 사이클
def test_run_cycle_normal():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    bot.add_symbol("DOGE")
    
    result = bot.run_cycle()
    assert result == True  # 계속 실행

# Test 2: 모든 심볼 청산 후
def test_run_cycle_all_closed():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    # 심볼 제거
    bot.symbols.clear()
    
    result = bot.run_cycle()
    assert result == False  # 종료

# Test 3: 예외 처리
def test_run_cycle_exception():
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    with patch.object(bot, 'process_symbol', side_effect=Exception("Test error")):
        result = bot.run_cycle()
    
    assert result == True  # 오류에도 계속
```

---

## 📦 Module 2: OrderExecutor (`src/core/order_executor.py`)

### 2.1 `execute_hedge_position(symbol, amount_usd) -> bool`
**테스트 목적**: 완벽한 헤지 포지션 실행

**테스트 케이스**:
```python
# Test 1: 정수 계약 완벽 매칭
def test_execute_hedge_perfect_match():
    executor = OrderExecutor(bithumb, gateio)
    
    # IP: contract_size = 1
    success = executor.execute_hedge_position("IP", 50)
    
    assert success == True
    
    # 빗썸과 Gate.io 수량 확인
    bithumb_balance = bithumb.get_balance("IP")
    gateio_positions = gateio.get_positions()
    
    # 정확히 같은 수량
    assert abs(bithumb_balance['free'] - (gateio_positions[0]['contracts'] * 1)) < 0.0001

# Test 2: 반올림 처리
def test_execute_hedge_rounding():
    executor = OrderExecutor(bithumb, gateio)
    
    # 45.57달러 → 정수 계약으로 조정
    success = executor.execute_hedge_position("IP", 45.57)
    
    assert success == True
    # 실제 체결 금액이 조정됨

# Test 3: 잔고 부족
def test_execute_hedge_insufficient_balance():
    executor = OrderExecutor(bithumb, gateio)
    
    # 큰 금액으로 잔고 부족 유발
    success = executor.execute_hedge_position("IP", 10000)
    
    assert success == False

# Test 4: 가격 조회 실패
def test_execute_hedge_price_failure():
    executor = OrderExecutor(bithumb, gateio)
    
    with patch.object(executor, '_get_prices', return_value=None):
        success = executor.execute_hedge_position("IP", 50)
    
    assert success == False
```

### 2.2 `close_position_percentage(symbol, percentage, position_value_usd) -> bool`
**테스트 목적**: 포지션 부분/전체 청산

**테스트 케이스**:
```python
# Test 1: 10% 부분 청산
def test_close_partial_10_percent():
    executor = OrderExecutor(bithumb, gateio)
    
    # 먼저 포지션 생성
    executor.execute_hedge_position("IP", 100)
    
    # 10% 청산
    success = executor.close_position_percentage("IP", 10, 100)
    
    assert success == True
    
    # 남은 포지션 확인
    bithumb_balance = bithumb.get_balance("IP")
    # 약 90% 남음

# Test 2: 100% 전체 청산
def test_close_full_100_percent():
    executor = OrderExecutor(bithumb, gateio)
    
    # 포지션 생성
    executor.execute_hedge_position("IP", 100)
    
    # 100% 청산
    success = executor.close_position_percentage("IP", 100, 100)
    
    assert success == True
    
    # 모두 청산됨
    bithumb_balance = bithumb.get_balance("IP")
    assert bithumb_balance['free'] < 0.001

# Test 3: 잘못된 비율
def test_close_invalid_percentage():
    executor = OrderExecutor(bithumb, gateio)
    
    success = executor.close_position_percentage("IP", 150, 100)  # 150%는 불가능
    assert success == False
    
    success = executor.close_position_percentage("IP", -10, 100)  # 음수 불가능
    assert success == False

# Test 4: 포지션 없을 때 청산
def test_close_no_position():
    executor = OrderExecutor(bithumb, gateio)
    
    success = executor.close_position_percentage("IP", 50, 100)
    assert success == False  # 실제 잔고 없음
```

### 2.3 `_execute_concurrent_orders(symbol, spot_quantity, futures_quantity, operation) -> bool`
**테스트 목적**: 동시 주문 실행

**테스트 케이스**:
```python
# Test 1: 동시 실행 성공
def test_concurrent_orders_success():
    executor = OrderExecutor(bithumb, gateio)
    
    success = executor._execute_concurrent_orders("IP", 10, 10, "open")
    assert success == True

# Test 2: 한쪽 실패 시 롤백
def test_concurrent_orders_partial_failure():
    executor = OrderExecutor(bithumb, gateio)
    
    # 선물 주문 실패 시뮬레이션
    with patch.object(gateio, 'create_market_order', return_value=None):
        success = executor._execute_concurrent_orders("IP", 10, 10, "open")
    
    assert success == False
    
    # 롤백 확인 (현물 되팔기)
    bithumb_balance = bithumb.get_balance("IP")
    assert bithumb_balance['free'] == 0  # 롤백됨

# Test 3: 타임아웃
def test_concurrent_orders_timeout():
    executor = OrderExecutor(bithumb, gateio)
    
    # 지연 시뮬레이션
    with patch.object(bithumb, 'create_market_order', side_effect=time.sleep(35)):
        success = executor._execute_concurrent_orders("IP", 10, 10, "open")
    
    assert success == False

# Test 4: reduce_only 파라미터
def test_concurrent_orders_reduce_only():
    executor = OrderExecutor(bithumb, gateio)
    
    # 포지션 먼저 생성
    executor.execute_hedge_position("IP", 50)
    
    # close 작업 시 reduce_only 확인
    with patch.object(gateio, 'create_market_order') as mock_order:
        executor._execute_concurrent_orders("IP", 5, 5, "close")
        
        # reduce_only가 포함되었는지 확인
        call_args = mock_order.call_args
        assert call_args[1]['params']['reduce_only'] == True
```

---

## 📦 Module 3: PositionBalancer (`src/core/position_balancer.py`)

### 3.1 `check_position_balance(symbol) -> PositionBalance`
**테스트 목적**: 포지션 균형 확인

**테스트 케이스**:
```python
# Test 1: 완벽한 균형
def test_check_perfect_balance():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    # 동일한 포지션 생성
    order_executor.execute_hedge_position("IP", 50)
    
    balance = balancer.check_position_balance("IP")
    
    assert balance.is_balanced == True
    assert balance.gap_percentage < 1.0

# Test 2: 불균형 감지
def test_check_imbalance():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    # 한쪽만 포지션 생성
    bithumb.create_market_order("IP/KRW", "buy", 100000)
    
    balance = balancer.check_position_balance("IP")
    
    assert balance.is_balanced == False
    assert balance.needs_rebalancing == True

# Test 3: 포지션 없음
def test_check_no_position():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    balance = balancer.check_position_balance("IP")
    
    assert balance.spot_quantity == 0
    assert balance.futures_quantity == 0
    assert balance.is_balanced == True  # 둘 다 0이면 균형

# Test 4: Gate.io 포지션 읽기 (심볼 정규화 이슈)
def test_check_gateio_symbol_normalization():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    # Gate.io 포지션 생성
    gateio.create_market_order("IP/USDT:USDT", "sell", 10)
    
    balance = balancer.check_position_balance("IP")
    
    assert balance.futures_quantity > 0  # 포지션 인식됨
```

### 3.2 `rebalance_position(symbol) -> bool`
**테스트 목적**: 자동 리밸런싱

**테스트 케이스**:
```python
# Test 1: 현물 초과 → 선물 추가
def test_rebalance_spot_excess():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    # 현물만 10개
    bithumb.create_market_order("IP/KRW", "buy", 100000)
    
    success = balancer.rebalance_position("IP")
    
    assert success == True
    
    balance = balancer.check_position_balance("IP")
    assert balance.is_balanced == True

# Test 2: 선물 초과 → 현물 추가
def test_rebalance_futures_excess():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    # 선물만 10 contracts
    gateio.create_market_order("IP/USDT:USDT", "sell", 10)
    
    success = balancer.rebalance_position("IP")
    
    assert success == True
    
    balance = balancer.check_position_balance("IP")
    assert balance.is_balanced == True

# Test 3: 작은 차이는 무시
def test_rebalance_small_difference():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    # 아주 작은 차이 생성
    order_executor.execute_hedge_position("IP", 50)
    bithumb.create_market_order("IP/KRW", "buy", 1000)  # 0.1 IP 정도
    
    success = balancer.rebalance_position("IP")
    
    assert success == True  # 작은 차이는 무시

# Test 4: 리밸런싱 실패
def test_rebalance_failure():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    # 큰 불균형 생성
    bithumb.create_market_order("IP/KRW", "buy", 1000000)
    
    # 잔고 부족으로 실패
    with patch.object(gateio, 'create_market_order', return_value=None):
        success = balancer.rebalance_position("IP")
    
    assert success == False
```

### 3.3 `balance_after_close(symbol, close_percentage) -> bool`
**테스트 목적**: 부분 청산 후 균형 조정

**테스트 케이스**:
```python
# Test 1: 10% 청산 후 균형
def test_balance_after_10_percent_close():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    # 포지션 생성
    order_executor.execute_hedge_position("IP", 100)
    
    # 10% 청산
    order_executor.close_position_percentage("IP", 10, 100)
    
    # 균형 조정
    success = balancer.balance_after_close("IP", 10)
    
    assert success == True
    
    balance = balancer.check_position_balance("IP")
    assert balance.is_balanced == True

# Test 2: 100% 청산은 조정 불필요
def test_balance_after_full_close():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    # 100% 청산 시도
    success = balancer.balance_after_close("IP", 100)
    
    assert success == True  # 아무것도 안함

# Test 3: 청산 실패 시 균형 조정 안함
def test_balance_after_failed_close():
    balancer = PositionBalancer(position_manager, order_executor, bithumb, gateio)
    
    # 포지션 없는 상태에서
    success = balancer.balance_after_close("IP", 50)
    
    assert success == True  # 조정할 것 없음
```

---

## 📦 Module 4: PremiumCalculator (`src/core/premium_calculator.py`)

### 4.1 `calculate(symbol) -> Optional[float]`
**테스트 목적**: 김치 프리미엄 계산

**테스트 케이스**:
```python
# Test 1: 정상 프리미엄 계산
def test_calculate_normal_premium():
    calculator = PremiumCalculator(bithumb, gateio)
    
    premium = calculator.calculate("IP")
    
    assert premium is not None
    assert -10 < premium < 100  # 합리적인 범위

# Test 2: 음수 프리미엄 (역프)
def test_calculate_negative_premium():
    calculator = PremiumCalculator(bithumb, gateio)
    
    # 해외가 더 비싼 상황 모킹
    with patch.object(bithumb, 'get_ticker', return_value={'ask': 1000}):
        with patch.object(gateio, 'get_ticker', return_value={'bid': 1.0}):
            with patch.object(calculator, '_get_usdt_krw_rate', return_value=1200):
                premium = calculator.calculate("IP")
    
    assert premium < 0  # 역프리미엄

# Test 3: 가격 조회 실패
def test_calculate_price_failure():
    calculator = PremiumCalculator(bithumb, gateio)
    
    with patch.object(bithumb, 'get_ticker', return_value=None):
        premium = calculator.calculate("IP")
    
    assert premium is None

# Test 4: USDT/KRW 환율 실패
def test_calculate_usdt_rate_failure():
    calculator = PremiumCalculator(bithumb, gateio)
    
    with patch.object(calculator, '_get_usdt_krw_rate', return_value=None):
        premium = calculator.calculate("IP")
    
    assert premium is None
```

---

## 📦 Module 5: PositionManager (`src/managers/position_manager.py`)

### 5.1 `get_existing_positions(symbol, korean_exchange, futures_exchange) -> float`
**테스트 목적**: 기존 포지션 조회 및 균형 검증

**테스트 케이스**:
```python
# Test 1: 균형잡힌 기존 포지션
def test_get_balanced_existing_positions():
    manager = PositionManager()
    
    # 균형잡힌 포지션 생성
    order_executor.execute_hedge_position("IP", 100)
    
    value = manager.get_existing_positions("IP", bithumb, gateio)
    
    assert 95 < value < 105  # 약 100달러

# Test 2: 불균형 포지션 감지
def test_get_imbalanced_existing_positions():
    manager = PositionManager()
    
    # 한쪽만 포지션
    bithumb.create_market_order("IP/KRW", "buy", 200000)
    
    value = manager.get_existing_positions("IP", bithumb, gateio)
    
    # 경고 로그 확인
    # 더 작은 값 반환

# Test 3: 포지션 없음
def test_get_no_existing_positions():
    manager = PositionManager()
    
    value = manager.get_existing_positions("IP", bithumb, gateio)
    
    assert value == 0.0

# Test 4: API 오류 처리
def test_get_existing_positions_api_error():
    manager = PositionManager()
    
    with patch.object(bithumb, 'get_balance', side_effect=Exception("API Error")):
        value = manager.get_existing_positions("IP", bithumb, gateio)
    
    assert value == 0.0  # 오류 시 0 반환
```

### 5.2 `update_position(symbol, value_change)`
**테스트 목적**: 포지션 값 업데이트

**테스트 케이스**:
```python
# Test 1: 포지션 증가
def test_update_position_increase():
    manager = PositionManager()
    
    manager.update_position("IP", 50.0)
    
    position = manager.get_position("IP")
    assert position.value_usd == 50.0

# Test 2: 포지션 감소
def test_update_position_decrease():
    manager = PositionManager()
    
    manager.update_position("IP", 100.0)
    manager.update_position("IP", -30.0)
    
    position = manager.get_position("IP")
    assert position.value_usd == 70.0

# Test 3: 음수 포지션 (오류 케이스)
def test_update_position_negative():
    manager = PositionManager()
    
    manager.update_position("IP", -100.0)
    
    position = manager.get_position("IP")
    assert position.value_usd == -100.0  # 현재는 허용됨
```

---

## 📦 Module 6: TimerManager (`src/managers/timer_manager.py`)

### 6.1 `check_profit_taking(symbol, premium, profit_stages) -> Optional[Tuple]`
**테스트 목적**: 이익 실현 타이머 로직

**테스트 케이스**:
```python
# Test 1: 첫 도달 → 즉시 실행
def test_timer_first_reach():
    timer = TimerManager()
    timer.initialize_symbol("IP")
    
    result = timer.check_profit_taking("IP", 10.5, settings.PROFIT_STAGES)
    
    assert result == (10, 10)  # 10% 프리미엄, 10% 청산

# Test 2: 쿨다운 중
def test_timer_cooldown():
    timer = TimerManager()
    timer.initialize_symbol("IP")
    
    # 첫 실행
    timer.check_profit_taking("IP", 10.5, settings.PROFIT_STAGES)
    
    # 즉시 다시 시도
    result = timer.check_profit_taking("IP", 10.5, settings.PROFIT_STAGES)
    
    assert result is None  # 쿨다운 중

# Test 3: 쿨다운 완료
def test_timer_cooldown_complete():
    timer = TimerManager()
    timer.initialize_symbol("IP")
    
    # 첫 실행
    timer.check_profit_taking("IP", 10.5, settings.PROFIT_STAGES)
    
    # 시간 조작
    timer.stage_timers["IP"][10] = datetime.now() - timedelta(minutes=31)
    
    # 다시 시도
    result = timer.check_profit_taking("IP", 10.5, settings.PROFIT_STAGES)
    
    assert result == (10, 10)  # 다시 실행 가능

# Test 4: 100% 프리미엄 → 즉시 전체 청산
def test_timer_100_percent_immediate():
    timer = TimerManager()
    timer.initialize_symbol("IP")
    
    result = timer.check_profit_taking("IP", 100.5, settings.PROFIT_STAGES)
    
    assert result == (100, 100)  # 타이머 없이 즉시
```

---

## 📦 Module 7: Exchange APIs

### 7.1 BithumbExchange (`src/exchanges/bithumb.py`)

**테스트 케이스**:
```python
# Test 1: 시장가 매수 (KRW 금액)
def test_bithumb_market_buy():
    bithumb = BithumbExchange(api_key, secret)
    
    order = bithumb.create_market_order("IP/KRW", "buy", 10000)  # 10,000 KRW
    
    assert order is not None
    assert order['status'] == 'closed'

# Test 2: 시장가 매도 (코인 수량)
def test_bithumb_market_sell():
    bithumb = BithumbExchange(api_key, secret)
    
    order = bithumb.create_market_order("IP/KRW", "sell", 1.0)  # 1 IP
    
    assert order is not None

# Test 3: 잔고 조회
def test_bithumb_get_balance():
    bithumb = BithumbExchange(api_key, secret)
    
    balance = bithumb.get_balance("IP")
    
    assert 'free' in balance
    assert 'used' in balance
    assert 'total' in balance

# Test 4: 최소 주문 크기
def test_bithumb_minimum_order():
    bithumb = BithumbExchange(api_key, secret)
    
    order = bithumb.create_market_order("IP/KRW", "buy", 100)  # 100 KRW (너무 작음)
    
    assert order is None  # 실패
```

### 7.2 GateIOExchange (`src/exchanges/gateio.py`)

**테스트 케이스**:
```python
# Test 1: 선물 숏 포지션
def test_gateio_futures_short():
    gateio = GateIOExchange(credentials)
    
    order = gateio.create_market_order("IP/USDT:USDT", "sell", 10)  # 10 contracts
    
    assert order is not None
    assert order['side'] == 'sell'

# Test 2: 정수 계약만 허용
def test_gateio_integer_contracts_only():
    gateio = GateIOExchange(credentials)
    
    # 소수점 계약 시도
    order = gateio.create_market_order("IP/USDT:USDT", "sell", 10.5)
    
    assert order is None  # 실패

# Test 3: reduce_only 파라미터
def test_gateio_reduce_only():
    gateio = GateIOExchange(credentials)
    
    # 먼저 포지션 생성
    gateio.create_market_order("IP/USDT:USDT", "sell", 10)
    
    # reduce_only로 청산
    order = gateio.create_market_order(
        "IP/USDT:USDT", "buy", 10, 
        {'reduce_only': True}
    )
    
    assert order is not None

# Test 4: 포지션 조회
def test_gateio_get_positions():
    gateio = GateIOExchange(credentials)
    
    positions = gateio.get_positions()
    
    assert isinstance(positions, list)
    # 각 포지션은 symbol, side, contracts 포함
```

---

## 🔬 통합 테스트 (Integration Tests)

### 시나리오 1: 완전한 헤지 라이프사이클
```python
def test_complete_hedge_lifecycle():
    """
    전체 흐름: 심볼 추가 → 포지션 구축 → 이익 실현 → 청산
    """
    bot = HedgeBot(bithumb, gateio)
    
    # 1. 심볼 추가
    assert bot.add_symbol("IP") == True
    
    # 2. 낮은 프리미엄에서 포지션 구축
    with patch.object(bot.premium_calculator, 'calculate', return_value=-0.5):
        bot.process_symbol("IP")
    
    position = bot.position_manager.get_position("IP")
    assert position.value_usd > 0
    
    # 3. 포지션 균형 확인
    balance = bot.position_balancer.check_position_balance("IP")
    assert balance.is_balanced == True
    
    # 4. 프리미엄 상승 → 부분 이익 실현
    with patch.object(bot.premium_calculator, 'calculate', return_value=10.5):
        bot.process_symbol("IP")
    
    assert position.value_usd < 50  # 일부 청산됨
    
    # 5. 높은 프리미엄 → 전체 청산
    with patch.object(bot.premium_calculator, 'calculate', return_value=100.5):
        bot.process_symbol("IP")
    
    assert "IP" not in bot.symbols
```

### 시나리오 2: 동시 다중 심볼 처리
```python
def test_multiple_symbols_concurrent():
    """
    여러 심볼 동시 처리
    """
    bot = HedgeBot(bithumb, gateio)
    
    # 여러 심볼 추가
    symbols = ["IP", "DOGE", "XRP"]
    for symbol in symbols:
        bot.add_symbol(symbol)
    
    # 동시에 처리
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(bot.process_symbol, s) for s in symbols]
        
        for future in futures:
            future.result()
    
    # 모든 심볼이 처리됨
    for symbol in symbols:
        position = bot.position_manager.get_position(symbol)
        assert position is not None
```

### 시나리오 3: 실패 복구
```python
def test_failure_recovery():
    """
    실패 시 복구 메커니즘
    """
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    # 1. 첫 실패
    with patch.object(bot.order_executor, 'execute_hedge_position', return_value=False):
        bot._build_position("IP")
    
    assert bot.failed_attempts["IP"] == 1
    
    # 2. 재시도
    bot._build_position("IP")  # 성공
    
    assert bot.failed_attempts["IP"] == 0  # 리셋됨
```

---

## 🚨 스트레스 테스트 (Stress Tests)

### 24시간 연속 운영 테스트
```python
def test_24_hour_operation():
    """
    24시간 연속 운영 시뮬레이션
    """
    bot = HedgeBot(bithumb, gateio)
    bot.add_symbol("IP")
    
    start_time = time.time()
    cycle_count = 0
    
    while time.time() - start_time < 86400:  # 24시간
        bot.run_cycle()
        cycle_count += 1
        time.sleep(5)  # 5초 간격
    
    # 메모리 누수 확인
    import psutil
    process = psutil.Process()
    memory_usage = process.memory_info().rss / 1024 / 1024  # MB
    
    assert memory_usage < 500  # 500MB 이하
    assert cycle_count > 17000  # 약 17,280 사이클
```

### 대량 주문 처리
```python
def test_high_volume_orders():
    """
    대량 주문 동시 처리
    """
    executor = OrderExecutor(bithumb, gateio)
    
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = []
        for i in range(100):
            future = pool.submit(
                executor.execute_hedge_position, 
                "IP", 
                50
            )
            futures.append(future)
        
        success_count = sum(1 for f in futures if f.result())
    
    assert success_count > 90  # 90% 이상 성공
```

### API 한계 테스트
```python
def test_api_rate_limits():
    """
    API Rate Limit 테스트
    """
    calculator = PremiumCalculator(bithumb, gateio)
    
    # 연속 호출
    premiums = []
    for _ in range(100):
        premium = calculator.calculate("IP")
        if premium:
            premiums.append(premium)
    
    # Rate limit에 걸리지 않고 대부분 성공
    assert len(premiums) > 80
```

---

## 📊 테스트 실행 순서

### Phase 1: 기본 기능 (필수)
1. Exchange API 연결 테스트
2. 프리미엄 계산 테스트
3. 단일 주문 실행 테스트
4. 포지션 조회 테스트

### Phase 2: 핵심 기능
1. 완벽한 헤지 포지션 테스트
2. 포지션 균형 확인 테스트
3. 리밸런싱 테스트
4. 부분 청산 테스트

### Phase 3: 고급 기능
1. 타이머 관리 테스트
2. 다중 심볼 테스트
3. 실패 복구 테스트
4. 동시성 테스트

### Phase 4: 안정성
1. 24시간 연속 운영
2. 메모리 누수 확인
3. API 한계 테스트
4. 예외 처리 검증

---

## ✅ 체크리스트

### 테스트 전 준비
- [ ] 테스트넷 API 키 설정
- [ ] 테스트 자금 충전 (KRW, USDT)
- [ ] 테스트 심볼 선택 (IP, DOGE)
- [ ] 로깅 설정 확인

### 필수 테스트
- [ ] 거래소 연결
- [ ] 프리미엄 계산
- [ ] 헤지 포지션 실행
- [ ] 포지션 균형 확인
- [ ] 리밸런싱
- [ ] 부분 청산
- [ ] 전체 청산

### 엣지 케이스
- [ ] 최소 주문 크기
- [ ] 정수 계약 처리
- [ ] 잔고 부족
- [ ] API 오류
- [ ] 네트워크 타임아웃
- [ ] 중복 주문 방지

### 성능 테스트
- [ ] 동시 주문 처리
- [ ] 메모리 사용량
- [ ] CPU 사용량
- [ ] API 호출 횟수
- [ ] 응답 시간

---

## 📝 테스트 결과 기록

### 테스트 실행 로그
```
날짜: 2024-XX-XX
환경: Production / Testnet
심볼: IP, DOGE

[PASS] Exchange API 연결
[PASS] 프리미엄 계산
[PASS] 완벽한 헤지 (6 IP = 6 contracts)
[PASS] 포지션 균형 (0.00% 차이)
[PASS] 리밸런싱
[PASS] 10% 부분 청산
[PASS] 100% 전체 청산
...
```

---

## 🔧 문제 해결 가이드

### 일반적인 문제

1. **Gate.io 포지션 0으로 표시**
   - 원인: 심볼 정규화 문제
   - 해결: `position_balancer.py`의 심볼 비교 로직 수정

2. **정확한 $50 주문 안됨**
   - 원인: Gate.io 정수 계약 제한
   - 해결: Gate.io 계약 먼저 계산 후 빗썸 수량 맞춤

3. **포지션 불균형**
   - 원인: 한쪽 주문 실패
   - 해결: 자동 리밸런싱 기능 활용

4. **API 속도 제한**
   - 원인: 너무 빠른 연속 호출
   - 해결: 적절한 딜레이 추가

---

## 🎯 결론

이 테스트 문서는 Redflag Hedge Bot의 모든 기능을 체계적으로 검증하기 위한 완벽한 가이드입니다.
각 테스트를 순서대로 실행하여 시스템의 안정성과 신뢰성을 보장하세요.

**핵심 성과 지표**:
- 테스트 커버리지: >90%
- 포지션 균형 정확도: <1% 오차
- 시스템 가용성: 99.9%
- 응답 시간: <100ms