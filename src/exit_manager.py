"""
Exit Strategy Manager - Automates position unwinding across exchanges
"""
import time
import json
import os
from typing import Dict
from datetime import datetime
from .korean_exchanges import KoreanExchangeManager
from .exchanges import ExchangeManager
from .position_tracker import PositionTracker
from .constants import MAX_MARKET_SLIPPAGE

class ExitManager:
    def __init__(self, exchange_manager: ExchangeManager, position_tracker: PositionTracker):
        self.exchange_manager = exchange_manager
        self.position_tracker = position_tracker
        self.korean_manager = KoreanExchangeManager()
        self.exit_state_file = "exit_state.json"
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
            "korean_orders": {},
            "overseas_positions": {},
            "filled_amounts": {},
            "status": "idle"
        }

    def save_exit_state(self):
        """Save exit state to file"""
        with open(self.exit_state_file, 'w') as f:
            json.dump(self.exit_state, f, indent=2)

    def initiate_exit(self, coin: str, distribution: Dict[str, float],
                     usdt_krw_rate: float = 1450.0) -> bool:
        """
        Initiate exit strategy after coins are transferred to Korean exchanges

        Args:
            coin: Coin symbol (e.g., 'BTC')
            distribution: {'bithumb': 0.5, 'upbit': 0.5} or {'bithumb': 1.0} etc.
            usdt_krw_rate: USDT price in KRW
        """
        print("\n🚀 EXIT STRATEGY 시작")
        print("="*50)

        # Get position data
        if not self.position_tracker.positions["entries"]:
            print("❌ No positions to exit")
            return False

        total_quantity = self.position_tracker.positions["total_quantity"]
        avg_price = self.position_tracker.positions["average_price"]

        # Calculate target prices
        target_prices = self.position_tracker.get_bithumb_targets(usdt_krw_rate)

        # Verify exchange health first
        print("\n🅾️ 거래소 상태 체크")
        for exchange in distribution.keys():
            if not self.korean_manager.verify_exchange_health(exchange):
                print(f"  ❌ {exchange.upper()} is not healthy, aborting")
                return False

        # Check balances on Korean exchanges
        print("\n📊 한국 거래소 잔고 확인")
        insufficient_balance = False
        for exchange, allocation in distribution.items():
            if allocation > 0:
                balance = self.korean_manager.check_balance(exchange, coin)
                required = total_quantity * allocation
                print(f"  {exchange.upper()}: {balance:.6f} {coin} (필요: {required:.6f})")

                if balance < required * 0.95:
                    print(f"  ⚠️ 잔고 부족! 전송 확인 필요")
                    insufficient_balance = True

        if insufficient_balance:
            print("\n⚠️ 경고: 일부 거래소에 충분한 잔고가 없습니다.")

        # Confirm before proceeding
        proceed = input("\n지정가 주문을 진행하시겠습니까? (y/n): ").strip().lower()
        if proceed != 'y':
            return False

        # Place limit orders on Korean exchanges
        print("\n📝 한국 거래소 지정가 주문 생성")
        korean_orders = self.korean_manager.place_limit_orders(
            coin=coin,
            total_quantity=total_quantity,
            target_prices=target_prices,
            distribution=distribution
        )

        if not korean_orders:
            print("❌ Failed to place any orders")
            return False

        # Store overseas positions info
        overseas_positions = self._get_overseas_positions(coin)

        # Update exit state
        self.exit_state = {
            "coin": coin,
            "korean_orders": korean_orders,
            "overseas_positions": overseas_positions,
            "filled_amounts": {ex: 0.0 for ex in distribution.keys()},
            "status": "monitoring",
            "start_time": datetime.now().isoformat(),
            "total_quantity": total_quantity,
            "average_price": avg_price
        }
        self.save_exit_state()

        print("\n✅ Exit strategy initiated. Starting monitoring...")
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
                        # Get contract size for proper conversion
                        contract_size = pos.get('contractSize', 1)  # Default to 1 if not available
                        contracts = pos.get('contracts', 0)

                        positions[exchange_name] = {
                            'contracts': contracts,
                            'contract_size': contract_size,
                            'coin_amount': contracts * contract_size,  # Convert to coin amount
                            'side': pos.get('side'),
                            'symbol': pos.get('symbol'),
                            'unwound': 0.0
                        }
                        print(f"  {exchange_name.upper()}: {contracts} contracts ({contracts * contract_size:.6f} {coin}) (short)")
                        break
            except Exception as e:
                print(f"  ⚠️ {exchange_name.upper()} position fetch failed: {e}")

        return positions

    def monitor_and_unwind(self, check_interval: int = 10):
        """Monitor Korean exchange fills and unwind overseas positions accordingly"""

        if self.exit_state.get('status') != 'monitoring':
            print("❌ No active exit strategy to monitor")
            return

        coin = self.exit_state['coin']
        korean_orders = self.exit_state['korean_orders']

        print(f"\n👀 모니터링 시작: {coin}")
        print("Press Ctrl+C to stop monitoring")

        try:
            while True:
                total_filled = 0
                fills_this_round = {}

                # Check Korean exchange order status
                for exchange, orders in korean_orders.items():
                    exchange_filled = 0

                    for order in orders:
                        if order.get('status') == 'closed':
                            continue

                        # Check order status
                        status = self.korean_manager.check_order_status(
                            exchange=exchange,
                            order_id=order['id'],
                            symbol=f"{coin}/KRW"
                        )

                        if status['status'] == 'closed' or status['filled'] > 0:
                            # Initialize 'filled' field if not present
                            if 'filled' not in order:
                                order['filled'] = 0

                            # Update order status
                            prev_filled = order['filled']
                            new_filled = status['filled'] - prev_filled

                            if new_filled > 0:
                                order['filled'] = status['filled']
                                order['status'] = status['status']
                                exchange_filled += new_filled

                                print(f"\n💰 {exchange.upper()} 체결: {new_filled:.6f} {coin} @ ₩{order['price']:,.0f}")

                    if exchange_filled > 0:
                        fills_this_round[exchange] = exchange_filled
                        self.exit_state['filled_amounts'][exchange] += exchange_filled
                        total_filled += exchange_filled

                # If we have new fills, unwind overseas positions
                if total_filled > 0:
                    self.save_exit_state()
                    self._unwind_overseas_positions(coin, total_filled)

                # Check if all orders are complete
                all_closed = True
                for exchange, orders in korean_orders.items():
                    for order in orders:
                        if order.get('status') != 'closed':
                            all_closed = False
                            break

                if all_closed:
                    print("\n🎉 모든 주문 체결 완료!")
                    self.exit_state['status'] = 'completed'
                    self.save_exit_state()
                    self._print_final_summary()
                    break

                # Status update
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Monitoring...")
                for exchange in korean_orders.keys():
                    filled = self.exit_state['filled_amounts'][exchange]
                    print(f"  {exchange.upper()}: {filled:.6f} {coin} 체결")

                time.sleep(check_interval)

        except KeyboardInterrupt:
            print("\n⏸️ Monitoring paused. Exit state saved.")
            self.save_exit_state()

    def _unwind_overseas_positions(self, coin: str, amount: float):
        """Unwind perpetual short positions on overseas exchanges"""

        print(f"\n🔄 해외 거래소 포지션 청산: {amount:.6f} {coin}")

        overseas_positions = self.exit_state['overseas_positions']
        remaining_to_unwind = amount

        for exchange_name, position in overseas_positions.items():
            if remaining_to_unwind <= 0.000001:  # Small threshold for float comparison
                break

            if position['side'] != 'short':
                continue

            # Calculate based on coin amounts, not contracts
            contract_size = position.get('contract_size', 1)
            unwound_coins = position['unwound'] * contract_size
            available_coins = position.get('coin_amount', position['contracts']) - unwound_coins

            if available_coins <= 0:
                continue

            coins_to_unwind = min(remaining_to_unwind, available_coins)
            contracts_to_unwind = coins_to_unwind / contract_size  # Convert back to contracts

            try:
                ex = self.exchange_manager.exchanges[exchange_name]['perp']
                symbol = position['symbol']

                # Get current price for slippage check
                ticker = ex.fetch_ticker(symbol)
                current_price = ticker['ask']  # Use ask price for buying

                # Close short position with reduce_only to avoid creating new position
                if exchange_name == 'bybit':
                    # Bybit uses reduceOnly parameter
                    order = ex.create_market_buy_order(
                        symbol=symbol,
                        amount=contracts_to_unwind,
                        params={
                            'reduceOnly': True,
                            'category': 'linear'
                        }
                    )
                elif exchange_name == 'okx':
                    # OKX uses reduceOnly flag
                    order = ex.create_market_buy_order(
                        symbol=symbol,
                        amount=contracts_to_unwind,
                        params={
                            'reduceOnly': True,
                            'tdMode': 'isolated'
                        }
                    )
                elif exchange_name == 'gateio':
                    # GateIO uses reduce_only
                    order = ex.create_market_buy_order(
                        symbol=symbol,
                        amount=contracts_to_unwind,
                        params={
                            'reduce_only': True,
                            'settle': 'usdt'
                        }
                    )
                else:
                    # Default fallback with reduce_only
                    order = ex.create_market_buy_order(
                        symbol=symbol,
                        amount=contracts_to_unwind,
                        params={'reduce_only': True}
                    )

                # Check for excessive slippage
                if order and 'average' in order:
                    fill_price = order['average']
                    slippage = abs(fill_price - current_price) / current_price
                    if slippage > MAX_MARKET_SLIPPAGE:
                        print(f"  ⚠️ High slippage detected: {slippage:.2%}")

                position['unwound'] += contracts_to_unwind
                remaining_to_unwind -= coins_to_unwind

                print(f"  ✅ {exchange_name.upper()}: {contracts_to_unwind:.6f} contracts ({coins_to_unwind:.6f} {coin}) 청산 (reduce_only)")

                # Save state after each unwind
                self.save_exit_state()

            except Exception as e:
                print(f"  ⚠️ {exchange_name.upper()} unwind failed: {e}")

        if remaining_to_unwind > 0:
            print(f"  ⚠️ Warning: {remaining_to_unwind:.6f} {coin} could not be unwound")

    def _print_final_summary(self):
        """Print final exit summary"""
        print("\n" + "="*60)
        print("📊 EXIT STRATEGY 최종 결과")
        print("="*60)

        coin = self.exit_state['coin']
        total_sold = sum(self.exit_state['filled_amounts'].values())
        avg_price = self.exit_state['average_price']

        print(f"\n코인: {coin}")
        print(f"총 판매량: {total_sold:.6f} {coin}")
        print(f"평균 매수가: ${avg_price:.2f}")

        print(f"\n한국 거래소 체결:")
        for exchange, amount in self.exit_state['filled_amounts'].items():
            if amount > 0:
                print(f"  {exchange.upper()}: {amount:.6f} {coin}")

        print(f"\n해외 거래소 청산:")
        for exchange, position in self.exit_state['overseas_positions'].items():
            if position['unwound'] > 0:
                print(f"  {exchange.upper()}: {position['unwound']:.6f} contracts")

        print("\n✅ Exit strategy completed successfully!")

    def resume_monitoring(self):
        """Resume monitoring from saved state"""
        if self.exit_state.get('status') == 'monitoring':
            print(f"📂 Resuming exit strategy for {self.exit_state['coin']}")
            self.monitor_and_unwind()
        else:
            print("❌ No active exit strategy to resume")