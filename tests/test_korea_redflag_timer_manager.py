from __future__ import annotations

from datetime import timedelta


def test_timer_manager_basic_flow() -> None:
    from overseas_exchange_hedge.korea.redflag.config.settings import settings
    from overseas_exchange_hedge.korea.redflag.managers.timer_manager import TimerManager

    tm = TimerManager()
    tm.timer_duration = timedelta(seconds=0)

    tm.initialize_symbol("BTC")
    # Verify timers exist for stages < 100
    levels = {p for p, _ in settings.PROFIT_STAGES if p < 100}
    assert set(tm.stage_timers["BTC"].keys()) == levels

    stage = tm.check_profit_taking("BTC", premium=999.0, profit_stages=[(100.0, 100.0)])
    assert stage is not None
    assert stage[0] == 100.0
