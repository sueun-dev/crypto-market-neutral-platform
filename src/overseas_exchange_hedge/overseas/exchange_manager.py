"""Exchange orchestration utilities for spot and perpetual venues."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
from typing import Any, Dict, Iterable, Optional, Set, Tuple, cast

import ccxt
import requests

from ..common.paths import cache_file
from ..config import EXCHANGES_CONFIG

logger = logging.getLogger(__name__)

OKX_STATUS_CACHE = "okx_status.json"
BYBIT_STATUS_CACHE = "bybit_status.json"


class ExchangeManager:
    """Initializes ccxt exchanges and resolves symbols/transferability."""

    def __init__(self) -> None:
        self.exchanges: Dict[str, Dict[str, ccxt.Exchange]] = {}
        self.symbols: Dict[str, Dict[str, Any]] = {}
        self.transferable: Dict[str, Dict[str, bool]] = {}
        self.transferable_chains: Dict[str, Dict[str, list[str]]] = {}
        self._last_okx_chains: list[str] = []
        self._last_bybit_chains: list[str] = []

    def initialize_exchanges(
        self,
        use_public_api: bool = False,
        allowed_exchanges: Optional[Iterable[str]] = None,
    ) -> Dict[str, Dict[str, ccxt.Exchange]]:
        """Initializes exchanges in parallel.

        Args:
            use_public_api: When True, skip credential injection.
            allowed_exchanges: Optional iterable to limit which exchanges are initialized.

        Returns:
            Mapping of exchange name to {"spot": Exchange, "perp": Exchange}.

        Raises:
            RuntimeError: If no exchanges could be initialized.
        """
        allowed_set: Optional[Set[str]] = {ex.lower() for ex in allowed_exchanges} if allowed_exchanges else None

        targets = [
            (exchange_name, config)
            for exchange_name, config in EXCHANGES_CONFIG.items()
            if allowed_set is None or exchange_name in allowed_set
        ]
        if not targets:
            raise RuntimeError("No exchanges selected for initialization.")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(targets))) as executor:
            futures = [
                executor.submit(self._connect_exchange, exchange_name, config, use_public_api)
                for exchange_name, config in targets
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()

        if not self.exchanges:
            raise RuntimeError("No exchanges available. Check API keys.")

        return self.exchanges

    def filter_spot_transferable(self, coin: str) -> None:
        """Removes spot symbols that cannot be deposited/withdrawn."""
        coin_code = coin.upper()
        self._last_okx_chains = []
        self._last_bybit_chains = []

        for exchange_name, exchange_pair in list(self.exchanges.items()):
            symbols = self.symbols.get(exchange_name, {})
            if "spot" not in symbols:
                continue

            transferable = False
            deposit_ok: Optional[bool] = None
            withdraw_ok: Optional[bool] = None

            try:
                ok_chains: list[str] = []
                if exchange_name == "okx":
                    deposit_ok, withdraw_ok = self._fetch_okx_transfer_flags(coin_code)
                if exchange_name == "bybit":
                    deposit_ok, withdraw_ok = self._fetch_bybit_transfer_flags(coin_code)

                if deposit_ok is None or withdraw_ok is None:
                    currencies = exchange_pair["spot"].fetch_currencies()
                    currency_info = currencies.get(coin_code) or currencies.get(coin_code.upper())
                    if currency_info:
                        dep_flag = currency_info.get("deposit")
                        wd_flag = currency_info.get("withdraw")
                        networks_dict = (
                            currency_info.get("networks") if isinstance(currency_info.get("networks"), dict) else {}
                        )
                        for net_code, net_info in networks_dict.items():
                            net_dep = net_info.get("deposit")
                            net_wd = net_info.get("withdraw")
                            if net_dep is True and net_wd is True:
                                ok_chains.append(str(net_code))
                                dep_flag = True
                                wd_flag = True

                        deposit_ok = dep_flag if deposit_ok is None else deposit_ok
                        withdraw_ok = wd_flag if withdraw_ok is None else withdraw_ok

                if withdraw_ok is False or deposit_ok is False:
                    transferable = False
                    logger.warning(
                        "⚠️ %s: %s 출금/입금 불가 → 현물 제외 (deposit=%s, withdraw=%s)",
                        exchange_name.upper(),
                        coin_code,
                        deposit_ok,
                        withdraw_ok,
                    )
                elif withdraw_ok is True and deposit_ok is not False:
                    transferable = True
                    if ok_chains:
                        logger.info(
                            "✅ %s: %s 출금 가능 (체인: %s)",
                            exchange_name.upper(),
                            coin_code,
                            ", ".join(ok_chains),
                        )
                    else:
                        logger.info("✅ %s: %s 출금 가능 (현물 사용)", exchange_name.upper(), coin_code)
                else:
                    logger.warning("⚠️ %s: %s 출금 정보 없음 → 현물 제외", exchange_name.upper(), coin_code)
            except Exception as exc:
                logger.warning("⚠️ %s: %s 입출금 조회 실패: %s", exchange_name.upper(), coin_code, exc)
                continue

            self.transferable.setdefault(exchange_name, {})[coin_code] = transferable
            if transferable:
                if exchange_name == "okx":
                    chains = self._last_okx_chains
                elif exchange_name == "bybit":
                    chains = self._last_bybit_chains
                elif exchange_name == "gateio":
                    chains = ok_chains
                else:
                    chains = []
                self.transferable_chains.setdefault(exchange_name, {})[coin_code] = chains or []
            else:
                self.transferable_chains.setdefault(exchange_name, {})[coin_code] = []

            if not transferable:
                symbols.pop("spot", None)
                symbols.pop("spot_market", None)
                if not symbols:
                    self.symbols.pop(exchange_name, None)

    def _fetch_okx_transfer_flags(self, coin_code: str) -> Tuple[Optional[bool], Optional[bool]]:
        """Retrieves deposit/withdraw flags for OKX via the public status API."""
        deposit_ok: Optional[bool] = None
        withdraw_ok: Optional[bool] = None
        headers = {"User-Agent": "hedge-bot/1.0"}
        max_pages = 16

        rows_iterable: list[Any] = []
        for page in range(1, max_pages + 1):
            url = f"https://www.okx.com/v2/asset/currency/status?page={page}"
            try:
                resp = requests.get(url, headers=headers, timeout=5)
                if resp.status_code != 200:
                    break
                payload = resp.json()
                data = payload.get("data")
                if isinstance(data, list):
                    rows = data
                else:
                    data = data or {}
                    rows = data.get("rows") or data.get("items") or data.get("list") or []
                if not rows:
                    break
                rows_iterable.extend(rows)
            except Exception:
                break

        if rows_iterable:
            self._save_okx_status_cache(rows_iterable)
        else:
            cached = self._load_okx_status_cache()
            if cached:
                rows_iterable = cached

        for row in rows_iterable:
            base_code = self._extract_okx_base(row.get("ccy") or row.get("currency") or row.get("symbol") or "")
            if base_code != coin_code:
                sub_lists = (
                    row.get("depositSubCurrencyList")
                    or row.get("withdrawSubCurrencyList")
                    or row.get("subCurrencyList")
                    or []
                )
                found_in_sub = any(
                    self._extract_okx_base(entry.get("symbol") or "") == coin_code for entry in sub_lists
                )
                if not found_in_sub:
                    continue

            dep_flag = row.get("canDep")
            wd_flag = row.get("canWd")
            dep_flag = row.get("canDeposit", dep_flag)
            wd_flag = row.get("canWithdraw", wd_flag)

            dep_status = row.get("rechargeableStatus")
            wd_status = row.get("withdrawableStatus")
            if dep_flag is None and isinstance(dep_status, (int, str)):
                dep_flag = str(dep_status) == "2"
            if wd_flag is None and isinstance(wd_status, (int, str)):
                wd_flag = str(wd_status) == "2"

            networks = (
                row.get("chains")
                or row.get("networks")
                or row.get("depositSubCurrencyList")
                or row.get("withdrawSubCurrencyList")
                or row.get("subCurrencyList")
                or []
            )
            ok_chains: list[str] = []
            if isinstance(networks, list):
                for net in networks:
                    net_base = self._extract_okx_base(net.get("symbol") or "")
                    if net_base and net_base != coin_code:
                        continue
                    net_dep = net.get("rechargeable") or net.get("canDep") or net.get("canDeposit")
                    net_wd = net.get("withdrawable") or net.get("canWd") or net.get("canWithdraw")
                    if net_dep is True and net_wd is True:
                        dep_flag = True
                        wd_flag = True
                        ok_chains.append(net.get("symbol") or net.get("chain") or "NETWORK")

            if dep_flag is not None and deposit_ok is None:
                deposit_ok = dep_flag
            if wd_flag is not None and withdraw_ok is None:
                withdraw_ok = wd_flag

            if deposit_ok is True and withdraw_ok is True:
                self._last_okx_chains = ok_chains
                return deposit_ok, withdraw_ok

        return deposit_ok, withdraw_ok

    def _fetch_bybit_transfer_flags(self, coin_code: str) -> Tuple[Optional[bool], Optional[bool]]:
        """Determines deposit/withdraw flags for Bybit from the local cache."""
        deposit_ok: Optional[bool] = None
        withdraw_ok: Optional[bool] = None

        rows_iterable = self._load_bybit_status_cache() or []

        for row in rows_iterable:
            sym = (row.get("symbol") or row.get("coin") or row.get("currency") or "").upper()
            if sym != coin_code:
                continue

            dep_flag = row.get("depositable") or row.get("rechargeable") or row.get("canDeposit") or row.get("canDep")
            wd_flag = row.get("withdrawable") or row.get("canWithdraw") or row.get("canWd")

            def _status_ok(val: Any, ok_values: set[int]) -> Optional[bool]:
                if val is None:
                    return None
                try:
                    return int(val) in ok_values
                except Exception:
                    if isinstance(val, bool):
                        return val if val is True else False
                return None

            dep_num = _status_ok(row.get("depositStatus"), {1})
            if dep_num is not None:
                dep_flag = dep_num
            networks = (
                row.get("coinChainStatusItem") or row.get("chains") or row.get("networks") or row.get("subCoins") or []
            )
            ok_chains: list[str] = []
            if isinstance(networks, list):
                for net in networks:
                    net_base = self._extract_okx_base(net.get("symbol") or net.get("coin") or "")
                    if net_base and net_base != coin_code:
                        continue
                    net_dep = (
                        net.get("depositable") or net.get("rechargeable") or net.get("canDeposit") or net.get("canDep")
                    )
                    net_wd = net.get("withdrawable") or net.get("canWithdraw") or net.get("canWd")
                    net_dep_num = _status_ok(net.get("depositStatus"), {1})
                    net_wd_num = _status_ok(net.get("withdrawStatus"), {1})
                    if net_dep_num is not None:
                        net_dep = net_dep_num
                    if net_wd_num is not None:
                        net_wd = net_wd_num
                    if net_dep is True and net_wd is True:
                        ok_chains.append(net.get("symbol") or net.get("chain") or "NETWORK")

            if ok_chains:
                dep_flag = True
                wd_flag = True
                logger.info("✅ BYBIT: %s 출금 가능 (체인: %s)", coin_code, ", ".join(ok_chains))
                self._last_bybit_chains = ok_chains

            if dep_flag is not None and deposit_ok is None:
                deposit_ok = dep_flag
            if wd_flag is not None and withdraw_ok is None:
                withdraw_ok = wd_flag
            if withdraw_ok is True and deposit_ok is True:
                return deposit_ok, withdraw_ok

        return deposit_ok, withdraw_ok

    @staticmethod
    def _load_okx_status_cache() -> Optional[list]:
        """Loads cached OKX status data if present."""
        path = cache_file(OKX_STATUS_CACHE, legacy_filename=OKX_STATUS_CACHE)
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return None

    @staticmethod
    def _save_okx_status_cache(rows: list) -> None:
        """Saves OKX status rows to disk."""
        path = cache_file(OKX_STATUS_CACHE, legacy_filename=OKX_STATUS_CACHE)
        try:
            with path.open("w", encoding="utf-8") as file:
                json.dump(rows, file, ensure_ascii=False)
        except Exception:
            return None

    @staticmethod
    def _load_bybit_status_cache() -> Optional[list]:
        """Loads the locally maintained Bybit status cache."""
        path = cache_file(BYBIT_STATUS_CACHE, legacy_filename=BYBIT_STATUS_CACHE)
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                if "result" in data and isinstance(data["result"], dict):
                    coins = data["result"].get("coins") or data["result"].get("rows") or data["result"].get("list")
                    if isinstance(coins, list):
                        return coins
                for key in ("data", "rows", "list", "coins"):
                    if isinstance(data.get(key), list):
                        return data[key]
        except Exception as exc:
            logger.warning("⚠️ BYBIT status cache load failed: %s", exc)
        return None

    @staticmethod
    def _save_bybit_status_cache(rows: list) -> None:
        """Saves Bybit status rows to disk."""
        path = cache_file(BYBIT_STATUS_CACHE, legacy_filename=BYBIT_STATUS_CACHE)
        try:
            with path.open("w", encoding="utf-8") as file:
                json.dump(rows, file, ensure_ascii=False)
        except Exception:
            return None

    @staticmethod
    def _extract_okx_base(symbol: str) -> str:
        """Extracts the base asset code from OKX status symbols."""
        if not symbol:
            return ""
        sym_upper = symbol.upper()
        match = re.match(r"([A-Z0-9]+)", sym_upper)
        if match:
            return match.group(1)
        if "-" in sym_upper:
            return sym_upper.split("-")[0]
        return sym_upper

    def _attach_credentials(
        self,
        params: Dict[str, Any],
        config: Dict[str, Any],
        password_key: Optional[str] = None,
    ) -> None:
        """Injects API credentials into a ccxt constructor params dictionary."""
        api_key = config.get("apiKey")
        secret = config.get("secret")
        if api_key and secret:
            params.update({"apiKey": api_key, "secret": secret})
        if password_key:
            password = config.get(password_key)
            if password:
                params[password_key] = password

    def _connect_exchange(self, exchange_name: str, config: Dict[str, Any], use_public_api: bool) -> None:
        """Connects to a single exchange and populates self.exchanges."""
        if use_public_api or (config["apiKey"] and config["secret"]):
            try:
                self._create_exchange_pair(exchange_name, config, use_public_api)
                logger.info("✅ %s connected", exchange_name.upper())
            except Exception as exc:
                logger.warning("⚠️ %s failed: %s", exchange_name.upper(), exc)

    def _create_exchange_pair(self, exchange_name: str, config: Dict[str, Any], use_public_api: bool) -> None:
        """Creates spot/perp exchange instances for the requested venue."""
        spot_params: Dict[str, Any]
        perp_params: Dict[str, Any]

        if exchange_name == "gateio":
            spot_params = {
                "options": config["spot_options"],
                "enableRateLimit": True,
            }
            perp_params = {
                "options": config["perp_options"],
                "enableRateLimit": True,
            }
            if not use_public_api:
                self._attach_credentials(spot_params, config)
                self._attach_credentials(perp_params, config)
            spot_exchange = cast(ccxt.Exchange, ccxt.gateio(cast(Any, spot_params)))
            perp_exchange = cast(ccxt.Exchange, ccxt.gateio(cast(Any, perp_params)))
            self.exchanges[exchange_name] = {"spot": spot_exchange, "perp": perp_exchange}

        elif exchange_name == "bybit":
            spot_params = {
                "options": {
                    "defaultType": "spot",
                    "recvWindow": 10000,
                    "adjustForTimeDifference": True,
                },
                "enableRateLimit": True,
            }
            perp_params = {
                "options": {
                    "defaultType": "linear",
                    "recvWindow": 10000,
                    "adjustForTimeDifference": True,
                },
                "enableRateLimit": True,
            }
            if not use_public_api:
                self._attach_credentials(spot_params, config)
                self._attach_credentials(perp_params, config)
            spot_exchange = cast(ccxt.Exchange, ccxt.bybit(cast(Any, spot_params)))
            perp_exchange = cast(ccxt.Exchange, ccxt.bybit(cast(Any, perp_params)))
            self.exchanges[exchange_name] = {"spot": spot_exchange, "perp": perp_exchange}

        elif exchange_name == "okx":
            spot_params = {
                "options": {
                    "defaultType": "spot",
                },
                "enableRateLimit": True,
            }
            perp_params = {
                "options": {
                    "defaultType": "swap",
                },
                "enableRateLimit": True,
            }
            if not use_public_api:
                self._attach_credentials(spot_params, config, password_key="password")
                self._attach_credentials(perp_params, config, password_key="password")
            spot_exchange = cast(ccxt.Exchange, ccxt.okx(cast(Any, spot_params)))
            perp_exchange = cast(ccxt.Exchange, ccxt.okx(cast(Any, perp_params)))
            self.exchanges[exchange_name] = {"spot": spot_exchange, "perp": perp_exchange}

    def load_markets_for_coin(self, coin: str) -> Dict[str, Dict[str, str]]:
        """Loads markets for a specific coin and validates symbols."""
        for exchange_name, exchange_pair in self.exchanges.items():
            try:
                exchange_pair["spot"].load_markets()
                exchange_pair["perp"].load_markets()

                config = EXCHANGES_CONFIG.get(exchange_name, {})
                spot_template = config.get("spot_symbol_template", "{coin}/USDT")
                perp_template = config.get("perp_symbol_template", "{coin}/USDT:USDT")

                spot_symbol = spot_template.format(coin=coin)
                perp_symbol = perp_template.format(coin=coin)

                self.symbols[exchange_name] = {}

                spot_symbols = exchange_pair["spot"].symbols or []
                spot_markets = exchange_pair["spot"].markets or {}
                if spot_symbol in spot_symbols:
                    self.symbols[exchange_name]["spot"] = spot_symbol
                    self.symbols[exchange_name]["spot_market"] = spot_markets.get(spot_symbol)
                    logger.info("✅ %s: %s (Spot)", exchange_name.upper(), spot_symbol)
                else:
                    logger.error("❌ %s: No spot market for %s", exchange_name.upper(), coin)

                perp_symbols = exchange_pair["perp"].symbols or []
                perp_markets = exchange_pair["perp"].markets or {}
                if perp_symbol in perp_symbols:
                    self.symbols[exchange_name]["perp"] = perp_symbol
                    self.symbols[exchange_name]["perp_market"] = perp_markets.get(perp_symbol)
                    logger.info("✅ %s: %s (Perp)", exchange_name.upper(), perp_symbol)
                else:
                    logger.error("❌ %s: No perp market for %s", exchange_name.upper(), coin)

                if not self.symbols[exchange_name]:
                    del self.symbols[exchange_name]
                    logger.warning("⚠️ %s: No markets available for %s", exchange_name.upper(), coin)

            except Exception as exc:
                logger.warning("⚠️ %s markets load failed: %s", exchange_name.upper(), exc)

        if not self.symbols:
            raise RuntimeError(f"No exchanges have {coin} trading pairs")

        return self.symbols

    def get_exchange(self, exchange_name: str) -> Optional[Dict[str, ccxt.Exchange]]:
        """Returns exchange instances by name."""
        return self.exchanges.get(exchange_name)

    def get_symbols(self, exchange_name: str) -> Optional[Dict[str, Any]]:
        """Returns symbols for a specific exchange."""
        return self.symbols.get(exchange_name)

    def resolve_symbol(self, exchange_name: str, market_type: str, coin: str) -> Optional[str]:
        """Resolves a formatted symbol for the given exchange and market type."""
        symbols = self.symbols.get(exchange_name)
        if symbols:
            candidate = symbols.get(market_type)
            if isinstance(candidate, str):
                return candidate

        config = EXCHANGES_CONFIG.get(exchange_name, {})
        template = config.get(f"{market_type}_symbol_template")
        if isinstance(template, str):
            return template.format(coin=coin)

        if market_type == "spot":
            return f"{coin}/USDT"
        if market_type == "perp":
            return f"{coin}/USDT:USDT"
        return None
