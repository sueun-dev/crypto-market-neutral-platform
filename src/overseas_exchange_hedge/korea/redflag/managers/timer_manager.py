"""이익 실현 타이머 관리 모듈."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Sequence, Tuple

from ..config.settings import settings

logger = logging.getLogger(__name__)


class TimerManager:
    """이익 실현 타이머를 관리하는 클래스"""

    def __init__(self):
        self.timer_duration = timedelta(minutes=settings.STAGE_TIMER_MINUTES)
        self.stage_timers: Dict[str, Dict[float, Optional[datetime]]] = {}

    def initialize_symbol(self, symbol: str) -> None:
        """심볼별 타이머를 초기화한다."""
        if symbol not in self.stage_timers:
            # settings.PROFIT_STAGES에서 동적으로 타이머 레벨 생성
            self.stage_timers[symbol] = {}
            for target_premium, _ in settings.PROFIT_STAGES:
                if target_premium < 100:  # 100% 이상은 즉시 실행이므로 타이머 불필요
                    self.stage_timers[symbol][target_premium] = None
            logger.info(f"{symbol} 타이머 초기화됨")

    def check_profit_taking(
        self, symbol: str, premium: float, profit_stages: Sequence[Tuple[float, float]]
    ) -> Optional[Tuple[float, float]]:
        """
        이익 실현 조건 확인

        Args:
            symbol: 심볼
            premium: 현재 프리미엄
            profit_stages: 이익 실현 단계 리스트

        Returns:
            (목표 프리미엄, 청산 비율) 또는 None
        """
        current_time = datetime.now()
        symbol_timers = self.stage_timers.get(symbol, {})

        for target_premium, close_percentage in profit_stages:
            # 프리미엄 도달 확인
            if premium >= target_premium:
                # 100% 이상 프리미엄은 즉시 청산
                if target_premium >= 100:
                    return target_premium, close_percentage

                # 타이머 확인 (None이면 처음 도달, 타이머가 있으면 쿨다운 체크)
                timer_start = symbol_timers.get(target_premium)

                if timer_start is None:
                    # 첫 도달, 즉시 실행하고 타이머 설정
                    self.set_timer(symbol, target_premium)
                    logger.info(
                        f"{symbol} {target_premium}% 프리미엄 도달, "
                        f"즉시 실행 후 {self.timer_duration.seconds // 60}분 쿨다운"
                    )
                    return target_premium, close_percentage

                # 쿨다운 시간이 지났는지 확인
                if current_time >= timer_start + self.timer_duration:
                    # 쿨다운 완료, 다시 실행 가능
                    self.set_timer(symbol, target_premium)  # 타이머 리셋
                    logger.info(f"{symbol} {target_premium}% 쿨다운 완료, 재실행")
                    return target_premium, close_percentage
                else:
                    # 아직 쿨다운 중
                    remaining = (timer_start + self.timer_duration) - current_time
                    logger.debug(f"{symbol} {target_premium}% 쿨다운 중 (남은 시간: {remaining.seconds // 60}분)")

        return None

    def set_timer(self, symbol: str, premium_level: float) -> None:
        """타이머를 현재 시각으로 설정한다."""
        if symbol in self.stage_timers:
            self.stage_timers[symbol][premium_level] = datetime.now()

    def remove_symbol(self, symbol: str) -> None:
        """심볼의 모든 타이머를 제거한다."""
        if symbol in self.stage_timers:
            del self.stage_timers[symbol]
            logger.info(f"{symbol} 타이머 제거됨")
