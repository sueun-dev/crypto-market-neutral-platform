"""
프로젝트 설정 관리
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from overseas_exchange_hedge.common.paths import log_file


@dataclass
class Settings:
    """전체 설정을 관리하는 클래스"""

    # 포지션 설정
    MAX_POSITION_USD: float = 3000.0  # 심볼당 최대 포지션 크기 (USD)
    POSITION_INCREMENT_USD: float = 30.0  # 포지션 증가 단위 (USD)

    # 프리미엄 임계값 설정 (%)
    BUILD_POSITION_PREMIUM: float = -2.0  # 포지션 구축 시작 프리미엄

    # 이익 실현 단계 (프리미엄%, 청산비율%)
    PROFIT_STAGES = [
        (0.5, 50),  # 0.5% 프리미엄에서 5% 청산
        (2.1, 10),  # 25% 프리미엄에서 10% 청산
        (3.2, 20),  # 33% 프리미엄에서 20% 청산
        (50, 40),  # 50% 프리미엄에서 40% 청산
        (100, 100),  # 100% 프리미엄에서 전체 청산
    ]

    # 타이머 설정
    STAGE_TIMER_MINUTES: int = 15  # 각 단계별 쿨다운 타이머 (분)
    MAIN_LOOP_INTERVAL: int = 14  # 메인 루프 간격 (초)

    # 거래소별 최소 주문 크기 (USD)
    MIN_ORDER_SIZES: Dict[str, float] = field(
        default_factory=lambda: {
            "upbit": 5.0,  # 5,000 KRW ≈ $5
            "bithumb": 1.0,  # 1,000 KRW ≈ $1
            "gateio": 10.0,  # $10 USD
            "bybit": 5.0,  # $5 USD
        }
    )

    # 재시도 설정
    MAX_FAILED_ATTEMPTS: int = 3  # 최대 실패 허용 횟수

    # 로깅 설정
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = str(log_file("redflag_hedge.log"))


# 전역 설정 인스턴스
settings = Settings()
