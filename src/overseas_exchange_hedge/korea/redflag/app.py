"""CLI entrypoint for the Redflag hedge bot."""

from __future__ import annotations

import logging
import os
import time
from typing import List, Tuple

from dotenv import load_dotenv

from .config.settings import settings
from .core import HedgeBot
from .exchanges.bithumb import BithumbExchange
from .exchanges.bybit import BybitExchange
from .exchanges.gateio import GateIOExchange
from .exchanges.upbit import UpbitExchange
from .utils import setup_logging

logger = logging.getLogger(__name__)


class RedflagHedgeBot:
    """메인 실행 클래스: 사용자 입력을 받아 봇을 구동한다."""

    def __init__(self):
        self.bot = None
        self.korean_exchange = None
        self.futures_exchange = None

    def get_user_input(self) -> Tuple[List[str], str, str]:
        """사용자 입력을 수집한다.

        Returns:
            심볼 리스트, 한국 거래소명, 선물 거래소명 튜플.
        """
        logger.info("=== 레드플래그 헤징 봇 ===")

        # 심볼 입력
        symbols_input = input("거래할 코인 심볼 (쉼표로 구분, 예: XRP,ETH,BTC): ").strip().upper()
        symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]

        # 한국 거래소 선택
        logger.info("한국 거래소 선택: 1. Upbit, 2. Bithumb")
        while True:
            choice = input("선택 (1-2): ").strip()
            if choice == "1":
                korean_exchange = "upbit"
                break
            elif choice == "2":
                korean_exchange = "bithumb"
                break
            logger.warning("1 또는 2를 입력해주세요.")

        # 선물 거래소 선택
        logger.info("선물 거래소 선택: 1. GateIO, 2. Bybit")
        while True:
            choice = input("선택 (1-2): ").strip()
            if choice == "1":
                futures_exchange = "gateio"
                break
            elif choice == "2":
                futures_exchange = "bybit"
                break
            logger.warning("1 또는 2를 입력해주세요.")

        return symbols, korean_exchange, futures_exchange

    def initialize_exchanges(self, korean_name: str, futures_name: str) -> bool:
        """선택된 거래소를 초기화한다.

        Args:
            korean_name: 한국 거래소 이름.
            futures_name: 선물 거래소 이름.

        Returns:
            성공 여부.
        """
        try:

            def _get_env(*names: str) -> str:
                for name in names:
                    value = os.getenv(name)
                    if value:
                        return value
                return ""

            # API 키 가져오기
            if korean_name == "upbit":
                korean_key = _get_env("UPBIT_API_KEY", "UPBIT_ACCESS_KEY")
                korean_secret = _get_env("UPBIT_API_SECRET", "UPBIT_SECRET_KEY")
            elif korean_name == "bithumb":
                korean_key = _get_env("BITHUMB_API_KEY")
                korean_secret = _get_env("BITHUMB_API_SECRET", "BITHUMB_SECRET_KEY")
            else:
                korean_key = _get_env(f"{korean_name.upper()}_API_KEY")
                korean_secret = _get_env(f"{korean_name.upper()}_API_SECRET")
            futures_key = _get_env(f"{futures_name.upper()}_API_KEY")
            futures_secret = _get_env(f"{futures_name.upper()}_API_SECRET")

            # 확인
            if not all([korean_key, korean_secret, futures_key, futures_secret]):
                logger.error("API 인증 정보가 .env 파일에 없습니다.")
                logger.error("필요한 환경변수:")
                if korean_name == "upbit":
                    logger.error("  UPBIT_API_KEY (또는 UPBIT_ACCESS_KEY)")
                    logger.error("  UPBIT_API_SECRET (또는 UPBIT_SECRET_KEY)")
                elif korean_name == "bithumb":
                    logger.error("  BITHUMB_API_KEY")
                    logger.error("  BITHUMB_API_SECRET (또는 BITHUMB_SECRET_KEY)")
                else:
                    logger.error(f"  {korean_name.upper()}_API_KEY")
                    logger.error(f"  {korean_name.upper()}_API_SECRET")
                logger.error(f"  {futures_name.upper()}_API_KEY")
                logger.error(f"  {futures_name.upper()}_API_SECRET")
                return False

            # 한국 거래소 초기화
            if korean_name == "upbit":
                self.korean_exchange = UpbitExchange(korean_key, korean_secret)
            elif korean_name == "bithumb":
                self.korean_exchange = BithumbExchange(korean_key, korean_secret)

            # 선물 거래소 초기화
            if futures_name == "gateio":
                self.futures_exchange = GateIOExchange({"apiKey": futures_key, "secret": futures_secret})
            elif futures_name == "bybit":
                self.futures_exchange = BybitExchange({"apiKey": futures_key, "secret": futures_secret})
            else:
                logger.error(f"지원하지 않는 선물 거래소: {futures_name}")
                return False

            logger.info(f"거래소 초기화 완료: {korean_name} + {futures_name}")
            return True

        except Exception as e:
            logger.error(f"거래소 초기화 실패: {e}")
            return False

    def run(self):
        """레드플래그 헤징 봇을 실행한다."""
        # 사용자 입력
        symbols, korean_exchange, futures_exchange = self.get_user_input()

        logger.info("거래소 초기화 시작")
        if not self.initialize_exchanges(korean_exchange, futures_exchange):
            logger.error("거래소 초기화 실패!")
            return

        # 헤징 봇 생성
        self.bot = HedgeBot(self.korean_exchange, self.futures_exchange)

        # 심볼 추가 및 검증
        logger.info("거래 페어 확인 시작")
        verified_count = 0
        for symbol in symbols:
            if self.bot.add_symbol(symbol):
                verified_count += 1
                logger.info(f"{symbol} 추가됨")
            else:
                logger.error(f"{symbol} 추가 실패")

        if verified_count == 0:
            logger.error("거래 가능한 심볼이 없습니다.")
            return

        logger.info(
            "거래 준비 완료 - 심볼: %s, 한국 거래소: %s, 선물 거래소: %s",
            ", ".join(self.bot.symbols),
            korean_exchange,
            futures_exchange,
        )
        logger.info(
            "설정 - 최대 포지션: $%s, 포지션 증가 단위: $%s, 타이머: %s분, 확인 간격: %s초",
            settings.MAX_POSITION_USD,
            settings.POSITION_INCREMENT_USD,
            settings.STAGE_TIMER_MINUTES,
            settings.MAIN_LOOP_INTERVAL,
        )

        logger.info("봇 실행 시작")

        # 메인 루프
        try:
            while True:
                # 한 사이클 실행
                continue_running = self.bot.run_cycle()

                if not continue_running:
                    logger.info("모든 포지션이 청산되었습니다. 거래 완료!")
                    break

                # 대기
                time.sleep(settings.MAIN_LOOP_INTERVAL)

        except KeyboardInterrupt:
            logger.info("사용자가 봇을 종료했습니다.")
        except Exception as e:
            logger.error(f"예상치 못한 오류: {e}")


def main() -> None:
    load_dotenv()
    setup_logging()
    bot = RedflagHedgeBot()
    bot.run()


if __name__ == "__main__":
    main()
