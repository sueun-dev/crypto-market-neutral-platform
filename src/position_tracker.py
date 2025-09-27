"""
Position tracker for calculating average prices and Bithumb target prices
"""
from typing import Dict
from datetime import datetime
import json
import os

class PositionTracker:
    def __init__(self):
        self.positions_file = "positions.json"
        self.positions = self.load_positions()

    def load_positions(self) -> Dict:
        """Load existing positions from file"""
        if os.path.exists(self.positions_file):
            try:
                with open(self.positions_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            "entries": [],
            "total_quantity": 0.0,
            "total_cost_usdt": 0.0,
            "average_price": 0.0,
            "current_coin": None
        }

    def save_positions(self):
        """Save positions to file"""
        with open(self.positions_file, 'w') as f:
            json.dump(self.positions, f, indent=2)

    def add_entry(self, coin: str, spot_price: float, quantity: float,
                  spot_exchange: str, perp_exchange: str, perp_price: float,
                  spread: float):
        """Add new hedge entry and calculate averages"""

        # Reset if different coin
        if self.positions["current_coin"] != coin:
            self.positions = {
                "entries": [],
                "total_quantity": 0.0,
                "total_cost_usdt": 0.0,
                "average_price": 0.0,
                "current_coin": coin
            }

        entry = {
            "timestamp": datetime.now().isoformat(),
            "coin": coin,
            "spot_price": spot_price,
            "quantity": quantity,
            "cost_usdt": spot_price * quantity,
            "spot_exchange": spot_exchange,
            "perp_exchange": perp_exchange,
            "perp_price": perp_price,
            "spread": spread
        }

        self.positions["entries"].append(entry)
        self.positions["total_quantity"] += quantity
        self.positions["total_cost_usdt"] += entry["cost_usdt"]
        self.positions["average_price"] = self.positions["total_cost_usdt"] / self.positions["total_quantity"]

        self.save_positions()
        return entry

    def get_bithumb_targets(self, usdt_krw_rate: float = 1450.0) -> Dict:
        """Calculate Bithumb target prices in KRW

        Args:
            usdt_krw_rate: USDT의 원화 가격 (빗썸/업비트에서의 USDT 가격)
        """
        if self.positions["average_price"] == 0:
            return None

        avg_price = self.positions["average_price"]
        total_quantity = self.positions["total_quantity"]
        total_cost_usdt = self.positions["total_cost_usdt"]

        # 손익분기점 (수수료 0.25% 고려)
        breakeven_price = avg_price * 1.0025

        # 목표 수익률별 가격 (순수 코인 김프)
        targets = {
            "average_price_usdt": avg_price,
            "total_quantity": total_quantity,
            "total_cost_usdt": total_cost_usdt,
            "breakeven_krw": breakeven_price * usdt_krw_rate,
            "target_1_percent": breakeven_price * 1.01 * usdt_krw_rate,
            "target_3_percent": breakeven_price * 1.03 * usdt_krw_rate,
            "target_5_percent": breakeven_price * 1.05 * usdt_krw_rate,
            "target_10_percent": breakeven_price * 1.10 * usdt_krw_rate,
        }

        return targets

    def display_position_summary(self, usdt_krw_rate: float = 1450.0):
        """Display current position summary"""
        if not self.positions["entries"]:
            print("\n📊 포지션 없음")
            return

        coin = self.positions["current_coin"]
        avg_price = self.positions["average_price"]
        total_qty = self.positions["total_quantity"]
        total_cost = self.positions["total_cost_usdt"]

        print(f"\n📊 현재 포지션 요약 ({coin})")
        print("="*50)
        print(f"  총 수량: {total_qty:.6f} {coin}")
        print(f"  총 비용: {total_cost:.2f} USDT")
        print(f"  평균 단가: ${avg_price:.2f}")
        print(f"  진입 횟수: {len(self.positions['entries'])}회")

        # 빗썸 목표가 계산
        targets = self.get_bithumb_targets(usdt_krw_rate)
        if targets:
            print(f"\n💰 빗썸 판매 목표가 (USDT ₩{usdt_krw_rate:,.0f} 기준)")
            print("="*50)
            print(f"  손익분기점: ₩{targets['breakeven_krw']:,.0f}")
            print(f"  +1% 수익: ₩{targets['target_1_percent']:,.0f}")
            print(f"  +3% 수익: ₩{targets['target_3_percent']:,.0f}")
            print(f"  +5% 수익: ₩{targets['target_5_percent']:,.0f}")
            print(f"  +10% 수익: ₩{targets['target_10_percent']:,.0f}")

            # 예상 수익 계산 (USDT 기준)
            print(f"\n💵 예상 수익 (5% 김프 기준)")
            print("="*50)
            revenue_krw = targets['target_5_percent'] * total_qty
            cost_krw = targets['breakeven_krw'] * total_qty
            profit_krw = revenue_krw - cost_krw
            profit_usdt = profit_krw / usdt_krw_rate

            print(f"  매도 금액: ₩{revenue_krw:,.0f}")
            print(f"  투자 금액: ₩{cost_krw:,.0f}")
            print(f"  순수익: ₩{profit_krw:,.0f} ({profit_usdt:,.2f} USDT)")