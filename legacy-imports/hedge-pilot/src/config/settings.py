from dataclasses import dataclass, field
from typing import Dict

@dataclass
class Settings:
    
    # 포지션 설정
    MAX_POSITION_USD: float = 2000.0  # 심볼당 최대 포지션 크기 (USD)
    POSITION_INCREMENT_USD: float = 50.0  # 포지션 증가 단위 (USD)
    
    # 프리미엄 임계값 설정 (%)
    BUILD_POSITION_PREMIUM: float = 0.15  # 포지션 구축 시작 프리미엄
    
    # 이익 실현 단계 (프리미엄%, 청산비율%)
    PROFIT_STAGES = [
        (10, 10),      # 18% 프리미엄에서 10% 청산
        (25, 10),    # 25% 프리미엄에서 10% 청산
        (33, 20),    # 33% 프리미엄에서 20% 청산
        (50, 40),    # 50% 프리미엄에서 40% 청산
        (100, 100),  # 100% 프리미엄에서 전체 청산
    ]
    
    # 타이머 설정
    STAGE_TIMER_MINUTES: int = 30  # 각 단계별 쿨다운 타이머 (분)
    MAIN_LOOP_INTERVAL: int = 5   # 메인 루프 간격 (초)
    
    # 거래소별 최소 주문 크기 (USD)
    MIN_ORDER_SIZES: Dict[str, float] = field(default_factory=lambda: {
        'upbit': 5.0,     # 5,000 KRW ≈ $5
        'bithumb': 5.0,   # 5,000 KRW ≈ $5
        'gateio': 10.0    # $10 USD
    })
    
    # 재시도 설정
    MAX_FAILED_ATTEMPTS: int = 3  # 최대 실패 허용 횟수
    
    # 포지션 균형 설정
    MAX_POSITION_GAP_USD: float = 10.0  # 허용 가능한 최대 포지션 갭 (USD)
    REBALANCE_THRESHOLD_USD: float = 15.0  # 리밸런싱 트리거 갭 (USD)
    MIN_RESIDUAL_USD: float = 5.0  # 청산 후 허용 잔여 포지션 (USD)
    
    # 로깅 설정
    LOG_LEVEL: str = 'INFO'
    LOG_FILE: str = 'redflag_hedge.log'


# 전역 설정 인스턴스
settings = Settings()