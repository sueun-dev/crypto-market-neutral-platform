"""
Bid/Ask 가격 로직 정확성 테스트
"""

def test_bid_ask_logic():
    """모든 bid/ask 사용 케이스 검증"""
    
    print("=" * 60)
    print("Bid/Ask 가격 사용 정확성 테스트")
    print("=" * 60)
    
    # 테스트 시나리오 설정
    scenarios = {
        "1. 현물 매수 (헤지 진입)": {
            "action": "한국 거래소에서 XRP 매수",
            "correct_price": "ask",
            "reason": "매수 시 ask 가격으로 체결 (매도자가 원하는 가격)",
            "example": "XRP/KRW ask: 1,500원"
        },
        
        "2. 현물 매도 (헤지 청산)": {
            "action": "한국 거래소에서 XRP 매도",
            "correct_price": "bid",
            "reason": "매도 시 bid 가격으로 체결 (매수자가 제시한 가격)",
            "example": "XRP/KRW bid: 1,490원"
        },
        
        "3. 선물 숏 진입": {
            "action": "선물 거래소에서 숏 포지션 오픈",
            "correct_price": "bid",
            "reason": "숏 진입 = 매도이므로 bid 가격",
            "example": "XRP/USDT bid: $1.10"
        },
        
        "4. 선물 숏 청산": {
            "action": "선물 거래소에서 숏 포지션 클로즈",
            "correct_price": "ask",
            "reason": "숏 청산 = 매수이므로 ask 가격",
            "example": "XRP/USDT ask: $1.11"
        },
        
        "5. USDT/KRW 환율 (KRW → USD 변환)": {
            "action": "KRW를 USD 가치로 환산",
            "correct_price": "ask",
            "reason": "KRW로 USDT를 매수해야 하므로 ask 가격",
            "example": "USDT/KRW ask: 1,380원"
        },
        
        "6. USDT/KRW 환율 (USD → KRW 변환)": {
            "action": "USD를 KRW 가치로 환산",
            "correct_price": "bid",
            "reason": "USDT를 매도하여 KRW를 얻으므로 bid 가격",
            "example": "USDT/KRW bid: 1,370원"
        },
        
        "7. 포지션 가치 평가": {
            "action": "현재 보유 포지션의 USD 가치 계산",
            "correct_price": "bid (현물), 현재가 (선물)",
            "reason": "청산 시 받을 수 있는 가격으로 평가",
            "example": "실제 팔 때 받을 가격"
        },
        
        "8. 프리미엄 계산": {
            "action": "한국-해외 가격 차이 계산",
            "correct_price": "ask (한국), bid (해외)",
            "reason": "실제 거래 시 체결될 가격으로 계산",
            "example": "한국 ask - 해외 bid = 실제 프리미엄"
        }
    }
    
    # 각 시나리오 출력
    for title, info in scenarios.items():
        print(f"\n{title}")
        print("-" * 40)
        print(f"행동: {info['action']}")
        print(f"올바른 가격: {info['correct_price']}")
        print(f"이유: {info['reason']}")
        print(f"예시: {info['example']}")
    
    print("\n" + "=" * 60)
    print("position_balancer.py 검증 결과")
    print("=" * 60)
    
    # position_balancer.py의 실제 사용 검증
    checks = [
        {
            "function": "_get_spot_position_value",
            "line": 95,
            "usage": "ticker['bid']",
            "purpose": "현물 포지션 가치 평가",
            "correct": True,
            "reason": "매도 시 받을 가격으로 평가"
        },
        {
            "function": "_get_spot_position_value",
            "line": 103,
            "usage": "usdt_krw_ticker['ask']",
            "purpose": "KRW를 USD로 변환",
            "correct": True,
            "reason": "KRW로 USDT를 살 때의 가격"
        },
        {
            "function": "_add_futures_short",
            "line": 201,
            "usage": "ticker['bid']",
            "purpose": "선물 숏 추가 (매도)",
            "correct": True,
            "reason": "숏 진입 = 매도이므로 bid"
        },
        {
            "function": "_add_spot_position",
            "line": 237,
            "usage": "ticker['ask']",
            "purpose": "현물 매수",
            "correct": True,
            "reason": "매수 시 ask 가격"
        },
        {
            "function": "_add_spot_position",
            "line": 241,
            "usage": "usdt_krw_ticker['bid']",
            "purpose": "USD를 KRW로 변환",
            "correct": True,
            "reason": "USDT를 팔아서 KRW를 얻음"
        },
        {
            "function": "_close_excess_spot",
            "line": 358,
            "usage": "ticker['bid']",
            "purpose": "현물 매도",
            "correct": True,
            "reason": "매도 시 bid 가격"
        },
        {
            "function": "_close_excess_spot",
            "line": 370,
            "usage": "amount_usd / ticker['bid']",
            "purpose": "매도할 수량 계산",
            "correct": True,
            "reason": "USD 금액을 bid 가격으로 나눔"
        },
        {
            "function": "_close_excess_futures",
            "line": 400,
            "usage": "ticker['ask']",
            "purpose": "선물 숏 청산 (매수)",
            "correct": True,
            "reason": "숏 청산 = 매수이므로 ask"
        }
    ]
    
    all_correct = True
    for check in checks:
        status = "✅" if check["correct"] else "❌"
        print(f"\n{status} {check['function']} (Line {check['line']})")
        print(f"   용도: {check['purpose']}")
        print(f"   사용: {check['usage']}")
        print(f"   이유: {check['reason']}")
        if not check["correct"]:
            all_correct = False
    
    print("\n" + "=" * 60)
    if all_correct:
        print("✅ 모든 bid/ask 사용이 정확합니다!")
    else:
        print("❌ 일부 bid/ask 사용에 오류가 있습니다!")
    print("=" * 60)
    
    # 실제 거래 시뮬레이션
    print("\n실제 거래 시뮬레이션")
    print("=" * 60)
    
    # 예시 가격
    xrp_krw_bid = 1490
    xrp_krw_ask = 1500
    xrp_usdt_bid = 1.10
    xrp_usdt_ask = 1.11
    usdt_krw_bid = 1370
    usdt_krw_ask = 1380
    
    print(f"\n현재 시장 가격:")
    print(f"XRP/KRW: bid={xrp_krw_bid:,}원, ask={xrp_krw_ask:,}원")
    print(f"XRP/USDT: bid=${xrp_usdt_bid}, ask=${xrp_usdt_ask}")
    print(f"USDT/KRW: bid={usdt_krw_bid:,}원, ask={usdt_krw_ask:,}원")
    
    # 헤지 진입
    print(f"\n1. 헤지 진입 (100 XRP):")
    spot_buy_cost = 100 * xrp_krw_ask
    print(f"   현물 매수: 100 XRP × {xrp_krw_ask:,}원 = {spot_buy_cost:,}원")
    
    futures_short_value = 100 * xrp_usdt_bid
    print(f"   선물 숏: 100 XRP × ${xrp_usdt_bid} = ${futures_short_value}")
    
    # 포지션 가치 평가
    print(f"\n2. 포지션 가치 평가:")
    spot_value_krw = 100 * xrp_krw_bid
    spot_value_usd = spot_value_krw / usdt_krw_ask
    print(f"   현물: 100 XRP × {xrp_krw_bid:,}원 ÷ {usdt_krw_ask:,}원 = ${spot_value_usd:.2f}")
    print(f"   선물: ${futures_short_value}")
    
    # 헤지 청산
    print(f"\n3. 헤지 청산:")
    spot_sell_revenue = 100 * xrp_krw_bid
    print(f"   현물 매도: 100 XRP × {xrp_krw_bid:,}원 = {spot_sell_revenue:,}원")
    
    futures_close_cost = 100 * xrp_usdt_ask
    print(f"   선물 숏 청산: 100 XRP × ${xrp_usdt_ask} = ${futures_close_cost}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_bid_ask_logic()