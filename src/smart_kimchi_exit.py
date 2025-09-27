"""
Smart Kimchi Exit Manager - 김프 기반 지능형 주문 관리
지정가 주문을 김프에 따라 자동 관리
"""
import time
import json
import os
from typing import Dict, Optional, List
from datetime import datetime
from .korean_exchanges import KoreanExchangeManager
from .exchanges import ExchangeManager
from .position_tracker import PositionTracker
from .kimchi_premium import KimchiPremiumCalculator

class SmartKimchiExit:
    def __init__(self, exchange_manager: ExchangeManager, position_tracker: PositionTracker):
        self.exchange_manager = exchange_manager
        self.position_tracker = position_tracker
        self.korean_manager = KoreanExchangeManager()
        self.premium_calculator = KimchiPremiumCalculator(exchange_manager, self.korean_manager)
        self.exit_state_file = "smart_kimchi_state.json"
        self.exit_state = self.load_exit_state()

    def load_exit_state(self) -> Dict:
        """Load exit state from file"""
        if os.path.exists(self.exit_state_file):
            try:
                with open(self.exit_state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Failed to load state: {e}")
        return {
            "active_orders": {},
            "completed_sales": [],
            "status": "idle"
        }

    def save_exit_state(self):
        """Save exit state to file"""
        with open(self.exit_state_file, 'w') as f:
            json.dump(self.exit_state, f, indent=2)

    def smart_order_management(self, coin: str, korean_exchanges: List[str],
                              premium_threshold: float = 3.0,
                              order_premium: float = 2.8,  # 주문 배치할 김프
                              check_interval: int = 10):
        """
        스마트 주문 관리 시스템
        - 김프 2.8% 이상: 지정가 주문 배치
        - 김프 3% 이상: 유지 (체결 대기)
        - 김프 2.8% 미만: 주문 취소

        Args:
            coin: 코인 심볼
            korean_exchanges: 한국 거래소 리스트
            premium_threshold: 목표 김프 (체결 허용)
            order_premium: 주문 배치 김프
            check_interval: 체크 주기
        """
        print("\n🤖 SMART KIMCHI EXIT MANAGER")
        print("="*60)
        print(f"코인: {coin}")
        print(f"주문 배치 김프: {order_premium}%")
        print(f"체결 허용 김프: {premium_threshold}%")
        print("="*60)

        # Get overseas positions
        overseas_positions = self._get_overseas_positions(coin)
        if not overseas_positions:
            print("❌ 해외 포지션 없음")
            return

        # Get total quantity from position tracker
        total_quantity = self.position_tracker.positions["total_quantity"]

        try:
            while True:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 김프 체크...")

                for korean_ex in korean_exchanges:
                    # Check balance
                    balance = self.korean_manager.check_balance(korean_ex, coin)
                    if balance < 0.0001:
                        continue

                    # Calculate current kimchi premium
                    best_premium = 0
                    best_overseas_ex = None

                    for overseas_ex in overseas_positions.keys():
                        premium, details = self.premium_calculator.calculate_kimchi_premium(
                            coin, korean_ex, overseas_ex
                        )
                        if premium and premium > best_premium:
                            best_premium = premium
                            best_overseas_ex = overseas_ex

                    print(f"\n{korean_ex.upper()} 현재 김프: {best_premium:.2f}%")

                    # Get active orders for this exchange
                    active_orders = self.exit_state.get('active_orders', {}).get(korean_ex, [])

                    # Decision logic
                    if best_premium >= order_premium:
                        # 김프가 충분함 - 주문 배치 또는 유지
                        if not active_orders:
                            # 주문이 없으면 배치
                            self._place_limit_orders(korean_ex, coin, balance, best_premium)
                        else:
                            # 주문 체결 상태 확인
                            self._check_order_fills(korean_ex, coin, active_orders, best_overseas_ex)

                            if best_premium >= premium_threshold:
                                print(f"  ✅ 김프 {best_premium:.2f}% - 체결 대기 중")
                            else:
                                print(f"  ⏳ 김프 {best_premium:.2f}% - 주문 유지")
                    else:
                        # 김프가 부족함 - 주문 취소
                        if active_orders:
                            print(f"  ⚠️ 김프 부족 ({best_premium:.2f}%) - 주문 취소")
                            self._cancel_all_orders(korean_ex, coin, active_orders)
                        else:
                            print(f"  ⏸️ 김프 부족 ({best_premium:.2f}%) - 대기")

                # Check if all positions are closed
                if self._check_completion():
                    print("\n🎉 모든 포지션 청산 완료!")
                    self.exit_state['status'] = 'completed'
                    self.save_exit_state()
                    break

                time.sleep(check_interval)

        except KeyboardInterrupt:
            print("\n⏸️ 중단됨. 상태 저장.")
            self.save_exit_state()

    def _place_limit_orders(self, exchange: str, coin: str, balance: float, current_premium: float):
        """지정가 주문 배치"""
        try:
            # Calculate target prices based on current premium
            current_price = self.korean_manager.get_current_price(exchange, coin)
            if not current_price:
                return

            orders = []

            # Place orders slightly above current price (to catch premium spikes)
            price_levels = [
                (current_price * 1.001, balance * 0.3),  # 0.1% 위
                (current_price * 1.002, balance * 0.3),  # 0.2% 위
                (current_price * 1.003, balance * 0.4),  # 0.3% 위
            ]

            for target_price, amount in price_levels:
                # Check minimum order value (5,000 KRW)
                if target_price * amount < 5000:
                    continue

                try:
                    symbol = f"{coin}/KRW"
                    order = self.korean_manager.exchanges[exchange].create_limit_sell_order(
                        symbol=symbol,
                        amount=amount,
                        price=int(target_price)  # 정수로 변환
                    )

                    orders.append({
                        'id': order['id'],
                        'price': target_price,
                        'amount': amount,
                        'filled': 0,
                        'status': 'open',
                        'timestamp': datetime.now().isoformat(),
                        'premium_at_placement': current_premium
                    })

                    print(f"  📝 지정가 주문: {amount:.6f} {coin} @ ₩{target_price:,.0f}")

                except Exception as e:
                    print(f"  ❌ 주문 실패: {e}")

            if orders:
                if 'active_orders' not in self.exit_state:
                    self.exit_state['active_orders'] = {}
                self.exit_state['active_orders'][exchange] = orders
                self.save_exit_state()

        except Exception as e:
            print(f"❌ 주문 배치 실패: {e}")

    def _cancel_all_orders(self, exchange: str, coin: str, orders: List[Dict]):
        """모든 주문 취소"""
        symbol = f"{coin}/KRW"
        canceled_count = 0

        for order in orders:
            if order.get('status') == 'open':
                success = self.korean_manager.cancel_order(
                    exchange, order['id'], symbol
                )
                if success:
                    order['status'] = 'canceled'
                    canceled_count += 1

        if canceled_count > 0:
            print(f"  🚫 {canceled_count}개 주문 취소 완료")
            # Clear active orders
            self.exit_state['active_orders'][exchange] = []
            self.save_exit_state()

    def _check_order_fills(self, exchange: str, coin: str, orders: List[Dict], overseas_ex: str):
        """주문 체결 확인 및 해외 포지션 청산"""
        symbol = f"{coin}/KRW"
        total_filled = 0

        for order in orders:
            if order.get('status') == 'closed':
                continue

            status = self.korean_manager.check_order_status(
                exchange, order['id'], symbol
            )

            if status['filled'] > order.get('filled', 0):
                new_fill = status['filled'] - order.get('filled', 0)
                order['filled'] = status['filled']
                order['status'] = status['status']
                total_filled += new_fill

                print(f"  💰 체결: {new_fill:.6f} {coin} @ ₩{order['price']:,.0f}")

                # Record sale
                self.exit_state['completed_sales'].append({
                    'timestamp': datetime.now().isoformat(),
                    'exchange': exchange,
                    'amount': new_fill,
                    'price': order['price']
                })

        # Unwind overseas positions if filled
        if total_filled > 0:
            self._unwind_overseas_position(overseas_ex, coin, total_filled)
            self.save_exit_state()

    def _unwind_overseas_position(self, exchange_name: str, coin: str, amount: float):
        """해외 포지션 청산"""
        try:
            ex = self.exchange_manager.exchanges[exchange_name]['perp']
            symbol = f"{coin}/USDT:USDT"

            # Close short position with market buy
            order = ex.create_market_buy_order(
                symbol=symbol,
                amount=amount,
                params={'reduce_only': True}
            )

            print(f"  ✅ {exchange_name.upper()} 숏 청산: {amount:.6f} {coin}")

        except Exception as e:
            print(f"  ❌ 청산 실패: {e}")

    def _get_overseas_positions(self, coin: str) -> Dict:
        """Get overseas positions"""
        positions = {}

        for exchange_name in self.exchange_manager.symbols.keys():
            if 'perp' not in self.exchange_manager.symbols[exchange_name]:
                continue

            try:
                ex = self.exchange_manager.exchanges[exchange_name]['perp']
                perp_positions = ex.fetch_positions()

                for pos in perp_positions:
                    if coin.upper() in pos.get('symbol', '').upper():
                        positions[exchange_name] = {
                            'contracts': pos.get('contracts', 0),
                            'side': pos.get('side'),
                            'symbol': pos.get('symbol')
                        }
                        break
            except:
                pass

        return positions

    def _check_completion(self) -> bool:
        """Check if all positions are closed"""
        # Check if there's any remaining balance
        for exchange in self.exit_state.get('active_orders', {}).keys():
            for coin in ['BTC', 'ETH', 'SOL']:  # Check common coins
                balance = self.korean_manager.check_balance(exchange, coin)
                if balance > 0.0001:
                    return False
        return True