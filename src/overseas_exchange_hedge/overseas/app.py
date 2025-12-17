"""Overseas (cross-exchange) entry & unwind flows."""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime
from typing import Dict, Iterable, Optional, Set, Tuple

import requests

from ..common import utils
from ..common.logging_utils import setup_logging
from ..config import ENTRY_AMOUNT, EXCHANGES_CONFIG, MAX_ENTRIES, PRICE_DIFF_THRESHOLD, SLEEP_SEC
from .exchange_manager import ExchangeManager
from .position_tracker import PositionTracker
from .price_analyzer import PriceAnalyzer
from .trade_executor import TradeExecutor

logger = logging.getLogger(__name__)

ALLOWED_EXCHANGES = ("gateio", "bybit", "okx")
PARTIAL_UNWIND_PNL_THRESHOLD = 0.015
PARTIAL_UNWIND_USD = 50.0


def run_overseas_unwind() -> None:
    """Closes overseas spot and perp positions in matched chunks across exchanges."""
    setup_logging()
    coin = ""
    while not coin:
        coin = input("청산할 코인 심볼 (예: BTC): ").strip().upper()
        if not coin:
            logger.error("❌ 코인 심볼을 반드시 입력해야 합니다.")

    spot_ex = input("\n스팟이 있는 거래소 (예: gateio/bybit/okx): ").strip().lower()
    perp_ex = input("선물이 있는 거래소 (예: gateio/bybit/okx): ").strip().lower()
    if spot_ex not in ("gateio", "bybit", "okx") or perp_ex not in ("gateio", "bybit", "okx"):
        logger.error("❌ 지원하지 않는 거래소입니다. (gateio/bybit/okx 중 선택)")
        return
    allowed = {spot_ex, perp_ex}

    chunk_usd = float(input("청산 단위(USD) [50]: ").strip() or "50")
    interval = float(input("청산 간격(초) [10]: ").strip() or "10")

    logger.info("\n청산 계획 확인:")
    logger.info("  코인: %s", coin)
    logger.info("  스팟 거래소: %s", spot_ex.upper())
    logger.info("  선물 거래소: %s", perp_ex.upper())
    logger.info("  청산 단위: $%s", chunk_usd)
    logger.info("  청산 간격: %s초", interval)
    if input("진행할까요? (y/n) [y]: ").strip().lower() not in ("", "y"):
        logger.info("취소되었습니다.")
        return

    mgr = ExchangeManager()
    mgr.initialize_exchanges(use_public_api=False, allowed_exchanges=allowed)
    mgr.load_markets_for_coin(coin)
    trade_executor = TradeExecutor(mgr)

    def _best_price(exchange, symbol: str, side: str) -> float:
        """
        side: 'sell' for spot (use bid), 'buy' for cover (use ask)
        """
        try:
            ob = exchange.fetch_order_book(symbol)
            if side == "sell":
                return float(ob["bids"][0][0]) if ob.get("bids") else 0.0
            return float(ob["asks"][0][0]) if ob.get("asks") else 0.0
        except Exception:
            try:
                ticker = exchange.fetch_ticker(symbol)
                return float(ticker.get("last") or 0.0)
            except Exception:
                return 0.0

    def _collect_spot_balances() -> Dict[str, float]:
        balances = {}
        for ex_name, pair in mgr.exchanges.items():
            syms = mgr.symbols.get(ex_name) or {}
            if "spot" not in syms:
                continue
            try:
                bal = pair["spot"].fetch_balance()
                coin_bal = bal.get(coin, {}) if isinstance(bal, dict) else {}
                qty = float(coin_bal.get("total") or 0)
                if qty > 0:
                    balances[ex_name] = qty
            except Exception:
                continue
        return balances

    def _collect_perp_qty() -> Dict[str, float]:
        qtys = {}
        for ex_name, pair in mgr.exchanges.items():
            syms = mgr.symbols.get(ex_name) or {}
            if "perp" not in syms:
                continue
            try:
                positions = pair["perp"].fetch_positions()
                pos_qty = 0.0
                for pos in positions or []:
                    sym = (pos.get("symbol") or "").upper()
                    if coin not in sym:
                        continue
                    contracts = pos.get("contracts")
                    size = pos.get("size")
                    contract_size = pos.get("contractSize") or 1
                    if contracts not in (None, 0):
                        pos_qty = abs(float(contracts) * float(contract_size))
                        break
                    if size not in (None, 0):
                        pos_qty = abs(float(size))
                        break
                if pos_qty > 0:
                    qtys[ex_name] = pos_qty
            except Exception:
                continue
        return qtys

    logger.info("\n🚩 해외 포지션 청산 시작 (스팟/퍼프 매칭)")
    while True:
        spot_bal = _collect_spot_balances()
        perp_qty = _collect_perp_qty()
        total_spot = sum(spot_bal.values())
        total_perp = sum(perp_qty.values())
        if total_spot <= 0 and total_perp <= 0:
            logger.info("✅ 청산 완료: 스팟/퍼프 보유 없음")
            break
        if total_spot <= 0 or total_perp <= 0:
            logger.warning(
                "⚠️ 스팟/퍼프 수량 불일치: spot=%s, perp=%s. 남은 퍼프/스팟은 수동 처리 필요.",
                total_spot,
                total_perp,
            )
            break

        # pick largest spot exchange and largest perp exchange for this chunk
        if spot_ex not in spot_bal or perp_ex not in perp_qty:
            logger.warning(
                "⚠️ 지정한 거래소의 수량 부족: spot=%s, perp=%s",
                spot_bal.get(spot_ex, 0),
                perp_qty.get(perp_ex, 0),
            )
            break

        # fetch prices
        spot_symbol = mgr.symbols[spot_ex]["spot"]
        perp_symbol = mgr.symbols[perp_ex]["perp"]
        spot_price = _best_price(mgr.exchanges[spot_ex]["spot"], spot_symbol, side="sell")
        perp_price = _best_price(mgr.exchanges[perp_ex]["perp"], perp_symbol, side="buy")
        ref_price = max(float(spot_price or 0), 1e-8)
        if ref_price <= 0 or perp_price <= 0:
            logger.warning("⚠️ 가격 조회 실패, 재시도 대기")
            time.sleep(interval)
            continue

        gross_spread = (perp_price - spot_price) / ref_price
        if abs(gross_spread) > 0.001:
            logger.info(
                "⏳ 스프레드 조건 미충족: spot %.6f, perp %.6f, 차이 %.3f%% (>0.10%%)",
                spot_price,
                perp_price,
                gross_spread * 100,
            )
            time.sleep(interval)
            continue

        qty_usd = chunk_usd
        qty_coin = qty_usd / ref_price
        max_match = min(spot_bal[spot_ex], perp_qty[perp_ex])
        # 남은 퍼프 USD가 chunk 이하이면 전량 청산
        remaining_usd = max_match * ref_price
        if remaining_usd <= chunk_usd:
            qty_coin = max_match
        else:
            qty_coin = min(qty_coin, max_match)
        if qty_coin <= 0:
            logger.warning("⚠️ 유효한 청산 수량이 없습니다. 종료.")
            break

        logger.info(
            "\n청산 청크 목표: %.6f %s (~$%.2f) | SPOT %s / PERP %s",
            qty_coin,
            coin,
            qty_coin * ref_price,
            spot_ex.upper(),
            perp_ex.upper(),
        )

        # 선물 커버 체결량 기준으로 스팟 매도
        filled_perp = 0.0
        try:
            filled_perp = trade_executor.execute_perp_cover(perp_ex, qty_coin, coin)
        except Exception as exc:
            logger.error("Perp 커버 실패: %s", exc)
            time.sleep(interval)
            continue

        if filled_perp <= 0:
            logger.warning("⚠️ Perp 커버 체결 없음, 재시도 대기")
            time.sleep(interval)
            continue

        spot_qty = min(filled_perp, spot_bal.get(spot_ex, 0))
        if spot_qty <= 0:
            logger.warning("⚠️ 스팟 수량 부족, 추가 커버는 중단")
            break

        try:
            trade_executor.execute_spot_sell(spot_ex, spot_qty, coin)
        except Exception as exc:
            logger.error("Spot 매도 실패: %s", exc)

        time.sleep(interval)


def _prompt_exchange_filters(entry_mode: str) -> Tuple[Optional[str], Optional[str], Optional[Set[str]]]:
    """Prompts for exchange filters in manual mode.

    Args:
        entry_mode: Entry mode selection ("auto" or "manual").

    Returns:
        Tuple of (spot_exchange_filter, perp_exchange_filter, selected_exchanges set or None).
    """
    spot_exchange_filter = None
    perp_exchange_filter = None
    selected_exchanges: Optional[Set[str]] = None

    if entry_mode == "manual":
        logger.info("\n사용 가능한 거래소: gateio, bybit, okx")

        spot_input = input("현물 거래소 지정 (예: gateio): ").strip().lower()
        perp_input = input("선물 거래소 지정 (예: bybit): ").strip().lower()

        if spot_input in ALLOWED_EXCHANGES:
            spot_exchange_filter = spot_input
            logger.info("현물: %s로 제한", spot_input.upper())
        else:
            logger.info("현물: 모든 거래소에서 검색")

        if perp_input in ALLOWED_EXCHANGES:
            perp_exchange_filter = perp_input
            logger.info("선물: %s로 제한", perp_input.upper())
        else:
            logger.info("선물: 모든 거래소에서 검색")

        selected: Set[str] = set()
        if spot_exchange_filter:
            selected.add(spot_exchange_filter)
        if perp_exchange_filter:
            selected.add(perp_exchange_filter)
        if selected:
            selected_exchanges = selected

    return spot_exchange_filter, perp_exchange_filter, selected_exchanges


def _prompt_coin() -> str:
    """Prompts for a target coin symbol."""
    coin = ""
    while not coin:
        coin = input("\n어떤 심볼을 분석할까요? (예: BTC): ").strip().upper()
        if not coin:
            logger.error("❌ 코인 심볼을 반드시 입력해야 합니다. 다시 입력해주세요.")
    logger.info("\n선택된 코인: %s", coin)
    return coin


def _validate_active_exchanges(selected_exchanges: Optional[Iterable[str]]) -> Tuple[Dict[str, bool], Iterable[str]]:
    """Validates API keys and returns active exchanges filtered by user selection.

    Args:
        selected_exchanges: Optional iterable of exchanges requested by the user.

    Returns:
        Tuple of (api_status mapping, active exchanges iterable).
    """
    api_status = utils.validate_api_keys(EXCHANGES_CONFIG)
    if selected_exchanges:
        missing_keys = [ex for ex in selected_exchanges if not api_status.get(ex)]
        if missing_keys:
            logger.error("❌ 선택한 거래소의 API 키가 없습니다:")
            for ex in missing_keys:
                logger.error("  • %s_API_KEY", ex.upper())
                logger.error("  • %s_API_SECRET", ex.upper())
                if ex == "okx":
                    logger.error("  • %s_API_PASSWORD", ex.upper())
            sys.exit(1)

    active_exchanges = [ex for ex, status in api_status.items() if status]
    if selected_exchanges:
        active_exchanges = [ex for ex in active_exchanges if ex in selected_exchanges]
    return api_status, active_exchanges


def _print_configuration(coin: str, active_exchanges: Iterable[str]) -> None:
    """Displays the current runtime configuration."""
    logger.info("Configuration")
    logger.info("Coin: %s", coin)
    logger.info("Active Exchanges: %s", ", ".join(ex.upper() for ex in active_exchanges))
    logger.info("Entry Amount: $%s", ENTRY_AMOUNT)
    logger.info("Max Entries: %s", MAX_ENTRIES)
    logger.info("Spread Threshold: %s", utils.format_percentage(PRICE_DIFF_THRESHOLD))


def _check_funding_rates(price_analyzer: PriceAnalyzer, entry_mode: str, perp_exchange_filter: Optional[str]) -> None:
    """Prints current funding rates for available perp markets.

    Args:
        price_analyzer: Price analyzer instance.
        entry_mode: Entry mode selection ("auto" or "manual").
        perp_exchange_filter: Optional filter limiting perp exchanges.
    """
    logger.info("\n📊 선물 펀딩비 체크 중...")
    logger.info("=" * 50)

    prices = price_analyzer.fetch_all_prices()
    has_negative_funding = False

    for exchange_name, price_data in prices.items():
        if entry_mode == "manual" and perp_exchange_filter and exchange_name != perp_exchange_filter:
            continue
        if "perp_bid" not in price_data:
            continue

        funding_rate = price_data.get("funding_rate")
        if funding_rate is None:
            logger.warning("%-10s 펀딩비: 데이터 없음 ⚠️", exchange_name.upper())
            continue
        status = "✅" if funding_rate >= 0 else "❌"
        logger.info("%-10s 펀딩비: %+0.4f%% %s", exchange_name.upper(), funding_rate * 100, status)
        if funding_rate < 0:
            has_negative_funding = True

    logger.info("=" * 50)
    if has_negative_funding:
        logger.warning("\n⚠️ 경고: 음수 펀딩비가 있는 거래소가 있습니다.")
        logger.warning("숏 포지션에서 펀딩비를 지불해야 할 수 있습니다.")


def _check_bithumb_transfer(coin: str) -> None:
    """Fetches Bithumb deposit/withdraw status and displays available chains."""
    url = "https://gw.bithumb.com/exchange/v1/coin-inout/info"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        payload = resp.json()
        coin_list = payload.get("data") or []
        target = next((c for c in coin_list if (c.get("coinSymbol") or "").upper() == coin.upper()), None)
        if not target:
            logger.warning("  BITHUMB: %s 정보 없음", coin)
            return

        networks = target.get("networkInfoList") or []
        ok_chains = [
            net.get("networkName") or net.get("networkKey") or "NETWORK"
            for net in networks
            if net.get("isDepositAvailable") is True and net.get("isWithdrawAvailable") is True
        ]
        dep_any = any(net.get("isDepositAvailable") for net in networks)
        wd_any = any(net.get("isWithdrawAvailable") for net in networks)

        if ok_chains:
            logger.info("  BITHUMB: 출금 가능 체인 - %s", ", ".join(ok_chains))
        else:
            status = "입금 가능" if dep_any else "입금 불가"
            status += " / "
            status += "출금 가능" if wd_any else "출금 불가"
            logger.info("  BITHUMB: %s", status)
    except Exception as exc:
        logger.warning("  BITHUMB: 상태 조회 실패 (%s)", exc)


def _maybe_partial_unwind(
    price_analyzer: PriceAnalyzer,
    trade_executor: TradeExecutor,
    position_tracker: PositionTracker,
    coin: str,
    prices: Dict[str, Dict[str, float]],
) -> None:
    """Attempts partial unwind when the PnL threshold is met.

    Args:
        price_analyzer: Price analyzer for spread calculations.
        trade_executor: Trade executor for executing unwind legs.
        position_tracker: Position tracker maintaining exposure.
        coin: Target asset symbol.
        prices: Latest price snapshot mapping.
    """
    open_pairs = position_tracker.get_open_pairs()
    for (spot_pair, perp_pair), summary in open_pairs.items():
        quantity_open = summary["quantity"]
        if quantity_open <= 0:
            continue
        exit_metrics = price_analyzer.calculate_exit_metrics(prices, spot_pair, perp_pair)
        if not exit_metrics:
            continue

        spot_entry_unit = summary["spot_cost"] / summary["quantity"]
        perp_entry_unit = summary["perp_proceed"] / summary["quantity"]
        entry_net_unit = spot_entry_unit - perp_entry_unit

        exit_spread_unit = exit_metrics["spot_exit"] - exit_metrics["perp_exit"]
        pnl_unit = exit_spread_unit - entry_net_unit
        if spot_entry_unit <= 0:
            continue
        pnl_ratio = pnl_unit / spot_entry_unit

        if pnl_ratio < PARTIAL_UNWIND_PNL_THRESHOLD:
            continue

        quantity_target = PARTIAL_UNWIND_USD / max(exit_metrics["spot_exit"], 1e-8)
        quantity_to_close = min(quantity_open, quantity_target)
        if quantity_to_close <= 1e-8:
            continue
        try:
            spot_filled = trade_executor.execute_spot_sell(spot_pair, quantity_to_close, coin)
            perp_filled = trade_executor.execute_perp_cover(perp_pair, quantity_to_close, coin)
            actual_qty = min(spot_filled, perp_filled)
            if actual_qty > 0:
                position_tracker.reduce_pair_position(spot_pair, perp_pair, actual_qty)
                usd_value = actual_qty * exit_metrics["spot_exit"]
                logger.info(
                    "\n💡 Partial unwind executed (%s / %s): %.6f %s (~$%.2f) | PnL ratio %.2f%%",
                    spot_pair.upper(),
                    perp_pair.upper(),
                    actual_qty,
                    coin,
                    usd_value,
                    pnl_ratio * 100,
                )
            else:
                logger.warning("⚠️ Partial unwind produced zero fill; skipping state update.")
        except Exception as exc:
            logger.warning("⚠️ Partial unwind failed: %s", exc)
        break


def _print_no_data_log(last_no_data_log: float) -> float:
    """Logs missing data at most every 30 seconds.

    Args:
        last_no_data_log: Timestamp of the last log entry.

    Returns:
        Updated timestamp (possibly unchanged).
    """
    now_ts = time.time()
    if now_ts - last_no_data_log >= 30:
        logger.info("[%s] 가격 데이터를 기다리는 중...", datetime.now().strftime("%H:%M:%S"))
        return now_ts
    return last_no_data_log


def _hedge_loop(
    coin: str,
    spot_exchange_filter: Optional[str],
    perp_exchange_filter: Optional[str],
    price_analyzer: PriceAnalyzer,
    trade_executor: TradeExecutor,
    position_tracker: PositionTracker,
) -> None:
    """Main monitoring/hedging loop.

    Args:
        coin: Target asset symbol.
        spot_exchange_filter: Optional spot exchange filter.
        perp_exchange_filter: Optional perp exchange filter.
        price_analyzer: Price analyzer instance.
        trade_executor: Trade executor instance.
        position_tracker: Position tracker instance.
    """
    entry_count = 0
    last_opportunity = None
    last_no_data_log = 0.0
    last_funding_rates: Dict[str, float] = {}

    while entry_count < MAX_ENTRIES:
        prices = price_analyzer.fetch_all_prices()
        (
            spot_ex,
            perp_ex,
            spot_price,
            perp_price,
            spread,
        ) = price_analyzer.find_best_hedge_opportunity_from_data(
            prices, spot_filter=spot_exchange_filter, perp_filter=perp_exchange_filter
        )

        if not spot_ex or not perp_ex or spot_price is None or perp_price is None or spread is None:
            last_no_data_log = _print_no_data_log(last_no_data_log)
            time.sleep(SLEEP_SEC)
            continue

        if spot_price == 0:
            time.sleep(SLEEP_SEC)
            continue

        gross_spread = (perp_price - spot_price) / spot_price
        last_no_data_log = 0.0
        status_flag = "READY" if spread >= PRICE_DIFF_THRESHOLD else "WAIT"
        summary_token = (spot_ex, perp_ex, round(gross_spread, 6), round(spread, 6), status_flag)

        if summary_token != last_opportunity:
            timestamp = datetime.now().strftime("%H:%M:%S")
            summary_line = (
                f"[{timestamp}] {spot_ex.upper()}→{perp_ex.upper()} "
                f"Gross {utils.format_percentage(gross_spread)}, "
                f"Net {utils.format_percentage(spread)} | {status_flag}"
            )
            logger.info(summary_line)
            last_opportunity = summary_token

            try:
                perp_symbol = price_analyzer.symbols[perp_ex]["perp"]
                funding_rate = price_analyzer.fetch_funding_rate(perp_ex, perp_symbol)
            except Exception:
                funding_rate = None

            if funding_rate is not None:
                prev_rate = last_funding_rates.get(perp_ex)
                if prev_rate is None or abs(prev_rate - funding_rate) >= 1e-6:
                    logger.info("    Funding %s: %+0.4f%%", perp_ex.upper(), funding_rate * 100)
                    last_funding_rates[perp_ex] = funding_rate

        _maybe_partial_unwind(price_analyzer, trade_executor, position_tracker, coin, prices)

        if spread < PRICE_DIFF_THRESHOLD:
            time.sleep(SLEEP_SEC)
            continue

        logger.info("\n🎯 조건 충족 – 헷지 주문 실행 중...")
        success = trade_executor.execute_hedge(
            spot_exchange=spot_ex,
            perp_exchange=perp_ex,
            spot_price=spot_price,
            perp_price=perp_price,
            coin=coin,
            entry_amount=ENTRY_AMOUNT,
        )

        if success:
            entry_count += 1
            estimated_qty = ENTRY_AMOUNT / spot_price
            position_tracker.add_entry(
                coin=coin,
                spot_price=spot_price,
                quantity=estimated_qty,
                spot_exchange=spot_ex,
                perp_exchange=perp_ex,
                perp_price=perp_price,
                spread=spread,
            )
            pos = position_tracker.positions
            logger.info(
                "  📦 누적 수량 %.6f %s, 평균단가 $%.2f (진입 %s/%s)",
                pos["total_quantity"],
                coin,
                pos["average_price"],
                len(pos["entries"]),
                MAX_ENTRIES,
            )
            logger.info("\n⏳ %s초 대기 후 다음 체크...", SLEEP_SEC)
        else:
            logger.warning("\n⚠️ 주문 실패 – %s초 후 재시도", SLEEP_SEC)

        time.sleep(SLEEP_SEC)

    logger.info("\n✅ Maximum entries (%s) reached. Bot stopped.", MAX_ENTRIES)


def run_overseas_entry(entry_mode: str) -> None:
    """Runs the overseas entry flow (auto/manual)."""
    setup_logging()
    entry_mode = (entry_mode or "").strip().lower()
    if entry_mode not in {"auto", "manual"}:
        raise ValueError("entry_mode must be 'auto' or 'manual'")

    spot_exchange_filter, perp_exchange_filter, selected_exchanges = _prompt_exchange_filters(entry_mode)
    coin = _prompt_coin()

    _, active_exchanges = _validate_active_exchanges(selected_exchanges)
    if not active_exchanges:
        logger.error("❌ No exchanges configured")
        logger.error("\nPlease set API keys in .env file:")
        for exchange in EXCHANGES_CONFIG.keys():
            logger.error("  • %s_API_KEY", exchange.upper())
            logger.error("  • %s_API_SECRET", exchange.upper())
            if exchange == "okx":
                logger.error("  • %s_API_PASSWORD", exchange.upper())
        sys.exit(1)

    _print_configuration(coin, active_exchanges)

    exchange_manager = ExchangeManager()
    exchange_manager.initialize_exchanges(allowed_exchanges=selected_exchanges)

    logger.info("Loading %s markets...", coin)
    exchange_manager.load_markets_for_coin(coin)
    exchange_manager.filter_spot_transferable(coin)

    # If manual spot exchange was chosen but filtered out, stop early
    if spot_exchange_filter and (
        spot_exchange_filter not in exchange_manager.symbols
        or "spot" not in exchange_manager.symbols.get(spot_exchange_filter, {})
    ):
        logger.error("❌ %s에서 %s 현물 입출금이 불가하여 거래를 중단합니다.", spot_exchange_filter.upper(), coin)
        sys.exit(1)

    # Ensure at least one spot exchange remains
    if not any("spot" in syms for syms in exchange_manager.symbols.values()):
        logger.error(
            "❌ 선택/활성 거래소에서 %s 현물 입출금이 불가합니다. .env 키 또는 거래소 설정을 확인하세요.",
            coin,
        )
        sys.exit(1)

    price_analyzer = PriceAnalyzer(exchange_manager)
    trade_executor = TradeExecutor(exchange_manager)
    position_tracker = PositionTracker()

    # 체인 정보 안내 (출금 가능 체인)
    logger.info("\n출금 가능 체인 안내:")
    for ex, syms in exchange_manager.symbols.items():
        if "spot" not in syms:
            continue
        chains = exchange_manager.transferable_chains.get(ex, {}).get(coin, [])
        chain_msg = ", ".join(chains) if chains else "정보 없음"
        logger.info("  %s: %s", ex.upper(), chain_msg)
    _check_bithumb_transfer(coin)

    _check_funding_rates(price_analyzer, entry_mode, perp_exchange_filter)

    proceed = input("\n계속 진행하시겠습니까? (y/n) [y]: ").strip().lower() or "y"
    if proceed != "y":
        logger.info("\n프로그램을 종료합니다.")
        sys.exit(0)

    logger.info("\n✅ System ready. Monitoring prices...\n")

    try:
        _hedge_loop(
            coin=coin,
            spot_exchange_filter=spot_exchange_filter,
            perp_exchange_filter=perp_exchange_filter,
            price_analyzer=price_analyzer,
            trade_executor=trade_executor,
            position_tracker=position_tracker,
        )
    except KeyboardInterrupt:
        logger.info("\n\n⛔ Bot stopped by user")
    except Exception as exc:
        logger.exception("\n❌ Fatal error: %s", exc)
        sys.exit(1)


def main() -> None:
    """Module entrypoint: runs overseas auto entry."""
    run_overseas_entry(entry_mode="auto")


if __name__ == "__main__":
    main()
