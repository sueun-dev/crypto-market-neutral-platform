"""
Kimchi Premium-based Exit Manager - Sells when premium reaches threshold
"""
import time
import json
import os
from typing import Dict, Optional
from datetime import datetime
from .korean_exchanges import KoreanExchangeManager
from .exchanges import ExchangeManager
from .position_tracker import PositionTracker
from .kimchi_premium import KimchiPremiumCalculator
from .constants import MAX_MARKET_SLIPPAGE

class KimchiExitManager:
    def __init__(self, exchange_manager: ExchangeManager, position_tracker: PositionTracker):
        self.exchange_manager = exchange_manager
        self.position_tracker = position_tracker
        self.korean_manager = KoreanExchangeManager()
        self.premium_calculator = KimchiPremiumCalculator(exchange_manager, self.korean_manager)
        self.exit_state_file = "kimchi_exit_state.json"
        self.exit_state = self.load_exit_state()

    def load_exit_state(self) -> Dict:
        """Load exit state from file"""
        if os.path.exists(self.exit_state_file):
            try:
                with open(self.exit_state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Failed to load exit state: {e}")
        return {
            "sales": [],
            "total_sold": {},
            "overseas_unwound": {},
            "status": "idle"
        }

    def save_exit_state(self):
        """Save exit state to file"""
        with open(self.exit_state_file, 'w') as f:
            json.dump(self.exit_state, f, indent=2)

    def initiate_kimchi_exit(self, coin: str, distribution: Dict[str, float],
                             premium_threshold: float = 3.0) -> bool:
        """
        Initiate kimchi premium-based exit strategy

        Args:
            coin: Coin symbol (e.g., 'BTC')
            distribution: {'bithumb': 0.5, 'upbit': 0.5} or {'bithumb': 1.0} etc.
            premium_threshold: Sell when premium reaches this percentage
        """
        print("\n🚀 KIMCHI PREMIUM EXIT STRATEGY 시작")
        print("="*50)
        print(f"목표 김프: {premium_threshold}% 이상에서 판매")

        # Get position data
        if not self.position_tracker.positions["entries"]:
            print("❌ No positions to exit")
            return False

        total_quantity = self.position_tracker.positions["total_quantity"]

        # Verify exchange health
        print("\n🆗️ 거래소 상태 체크")
        for exchange in distribution.keys():
            if not self.korean_manager.verify_exchange_health(exchange):
                print(f"  ❌ {exchange.upper()} is not healthy")
                return False

        # Check balances
        print("\n📊 한국 거래소 잔고 확인")
        for exchange, allocation in distribution.items():
            if allocation > 0:
                balance = self.korean_manager.check_balance(exchange, coin)
                required = total_quantity * allocation
                print(f"  {exchange.upper()}: {balance:.6f} {coin} (필요: {required:.6f})")

                if balance < required * 0.95:
                    print(f"  ⚠️ 잔고 부족! 전송 확인 필요")

        # Store overseas positions info
        overseas_positions = self._get_overseas_positions(coin)
        if not overseas_positions:
            print("❌ No overseas positions found")
            return False

        # Initialize exit state
        self.exit_state = {
            "coin": coin,
            "distribution": distribution,
            "premium_threshold": premium_threshold,
            "overseas_positions": overseas_positions,
            "total_quantity": total_quantity,
            "total_sold": {ex: 0.0 for ex in distribution.keys()},
            "overseas_unwound": {ex: 0.0 for ex in overseas_positions.keys()},
            "sales": [],
            "status": "monitoring",
            "start_time": datetime.now().isoformat()
        }
        self.save_exit_state()

        print("\n✅ Kimchi exit strategy initiated")
        return True

    def _get_overseas_positions(self, coin: str) -> Dict:
        """Get current perpetual positions on overseas exchanges"""
        positions = {}

        for exchange_name in self.exchange_manager.symbols.keys():
            if 'perp' not in self.exchange_manager.symbols[exchange_name]:
                continue

            try:
                ex = self.exchange_manager.exchanges[exchange_name]['perp']
                perp_positions = ex.fetch_positions()

                for pos in perp_positions:
                    if coin.upper() in pos.get('symbol', '').upper():
                        contract_size = pos.get('contractSize', 1)
                        contracts = pos.get('contracts', 0)

                        positions[exchange_name] = {
                            'contracts': contracts,
                            'contract_size': contract_size,
                            'coin_amount': contracts * contract_size,
                            'side': pos.get('side'),
                            'symbol': pos.get('symbol'),
                            'entry_price': pos.get('markPrice', pos.get('entryPrice'))
                        }
                        print(f"  {exchange_name.upper()}: {contracts} contracts @ ${positions[exchange_name]['entry_price']:.2f}")
                        break
            except Exception as e:
                print(f"  ⚠️ {exchange_name.upper()} position fetch failed: {e}")

        return positions

    def monitor_and_execute(self, check_interval: int = 10, sell_portion: float = 0.5):
        """
        Monitor kimchi premium and execute trades when threshold is met

        Args:
            check_interval: Seconds between checks
            sell_portion: Portion to sell when premium threshold is met (0.5 = 50%)
        """
        if self.exit_state.get('status') != 'monitoring':
            print("❌ No active exit strategy to monitor")
            return

        coin = self.exit_state['coin']
        distribution = self.exit_state['distribution']
        premium_threshold = self.exit_state['premium_threshold']
        overseas_positions = self.exit_state['overseas_positions']

        print(f"\n👀 김치 프리미엄 모니터링 시작: {coin}")
        print(f"판매 조건: 김프 {premium_threshold}% 이상")
        print(f"판매 비중: {sell_portion*100}% 씩")
        print("Press Ctrl+C to stop monitoring")

        try:
            while True:
                # Calculate current premiums
                korean_exchanges = list(distribution.keys())
                results = self.premium_calculator.monitor_premium(
                    coin, korean_exchanges, overseas_positions, premium_threshold
                )

                # Find best opportunity
                best = self.premium_calculator.get_best_opportunity(results)

                if best:
                    print(f"\n🔥 김프 {best['premium']:.2f}% 달성!")
                    print(f"최적 경로: {best['korean_exchange'].upper()} 매도, {best['overseas_exchange'].upper()} 청산")

                    # Execute market sell on Korean exchange
                    korean_ex = best['korean_exchange']
                    allocation = distribution[korean_ex]
                    total_quantity = self.exit_state['total_quantity']

                    # Calculate amount to sell this round
                    already_sold = self.exit_state['total_sold'][korean_ex]
                    available = (total_quantity * allocation) - already_sold
                    sell_amount = min(available, total_quantity * allocation * sell_portion)

                    if sell_amount > 0.0001:  # Minimum amount check
                        success = self._execute_market_sell(korean_ex, coin, sell_amount, best['details'])

                        if success:
                            # Unwind corresponding overseas position
                            self._unwind_overseas_position(
                                best['overseas_exchange'],
                                coin,
                                sell_amount
                            )

                            # Check if fully exited
                            total_sold_all = sum(self.exit_state['total_sold'].values())
                            if total_sold_all >= self.exit_state['total_quantity'] * 0.99:
                                print("\n🎉 모든 포지션 청산 완료!")
                                self.exit_state['status'] = 'completed'
                                self.save_exit_state()
                                self._print_final_summary()
                                break
                    else:
                        print(f"⚠️ {korean_ex.upper()}에 판매 가능한 물량 없음")

                # Status update
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Status:")
                for ex in distribution.keys():
                    sold = self.exit_state['total_sold'][ex]
                    target = self.exit_state['total_quantity'] * distribution[ex]
                    print(f"  {ex.upper()}: {sold:.6f}/{target:.6f} {coin} 판매")

                time.sleep(check_interval)

        except KeyboardInterrupt:
            print("\n⏸️ Monitoring paused. Exit state saved.")
            self.save_exit_state()

    def _execute_market_sell(self, exchange: str, coin: str, amount: float, details: Dict) -> bool:
        """Execute market sell on Korean exchange"""
        try:
            ex = self.korean_manager.exchanges[exchange]
            symbol = f"{coin}/KRW"

            # Place market sell order
            order = ex.create_market_sell_order(symbol, amount)

            if order:
                fill_price = order.get('average', order.get('price', details['korean_bid_price']))

                # Record sale
                sale_record = {
                    'timestamp': datetime.now().isoformat(),
                    'exchange': exchange,
                    'amount': amount,
                    'price_krw': fill_price,
                    'premium': details['kimchi_premium'],
                    'order_id': order.get('id')
                }
                self.exit_state['sales'].append(sale_record)
                self.exit_state['total_sold'][exchange] += amount
                self.save_exit_state()

                print(f"✅ {exchange.upper()} 시장가 매도: {amount:.6f} {coin} @ ₩{fill_price:,.0f}")
                print(f"   김프: {details['kimchi_premium']:.2f}%")
                return True

        except Exception as e:
            print(f"❌ {exchange.upper()} 매도 실패: {e}")
            return False

    def _unwind_overseas_position(self, exchange_name: str, coin: str, amount: float):
        """Unwind overseas perpetual position"""
        try:
            position = self.exit_state['overseas_positions'][exchange_name]
            if position['side'] != 'short':
                return

            ex = self.exchange_manager.exchanges[exchange_name]['perp']
            symbol = position['symbol']

            # Convert coin amount to contracts
            contract_size = position.get('contract_size', 1)
            contracts_to_unwind = amount / contract_size

            # Close position with reduce_only
            params = {'reduce_only': True}
            if exchange_name == 'bybit':
                params['category'] = 'linear'
            elif exchange_name == 'okx':
                params['tdMode'] = 'isolated'
            elif exchange_name == 'gateio':
                params['settle'] = 'usdt'

            order = ex.create_market_buy_order(symbol, contracts_to_unwind, params=params)

            if order:
                self.exit_state['overseas_unwound'][exchange_name] += amount
                self.save_exit_state()
                print(f"✅ {exchange_name.upper()}: {contracts_to_unwind:.6f} contracts 청산")

        except Exception as e:
            print(f"⚠️ {exchange_name.upper()} 청산 실패: {e}")

    def _print_final_summary(self):
        """Print final exit summary"""
        print("\n" + "="*60)
        print("📊 KIMCHI EXIT STRATEGY 최종 결과")
        print("="*60)

        coin = self.exit_state['coin']
        total_sold = sum(self.exit_state['total_sold'].values())

        print(f"\n코인: {coin}")
        print(f"총 판매량: {total_sold:.6f} {coin}")

        print(f"\n한국 거래소 판매:")
        for exchange, amount in self.exit_state['total_sold'].items():
            if amount > 0:
                print(f"  {exchange.upper()}: {amount:.6f} {coin}")

        print(f"\n해외 거래소 청산:")
        for exchange, amount in self.exit_state['overseas_unwound'].items():
            if amount > 0:
                print(f"  {exchange.upper()}: {amount:.6f} {coin}")

        if self.exit_state['sales']:
            avg_premium = sum(s['premium'] for s in self.exit_state['sales']) / len(self.exit_state['sales'])
            print(f"\n평균 김치 프리미엄: {avg_premium:.2f}%")

        print("\n✅ Kimchi exit strategy completed!")

    def resume_monitoring(self):
        """Resume monitoring from saved state"""
        if self.exit_state.get('status') == 'monitoring':
            print(f"📂 Resuming kimchi exit for {self.exit_state['coin']}")
            self.monitor_and_execute()
        else:
            print("❌ No active exit strategy to resume")