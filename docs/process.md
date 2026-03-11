전체 시스템 동작 정리
====================

이 프로젝트는 `src/` 레이아웃을 사용한다. 주요 실행 진입점은 통합 CLI(`uv run market-neutral`)이며, 각 워크플로는 모듈로 분리되어 있다.

프로젝트 구조(핵심)
------------------
- `src/overseas_exchange_hedge/`
  - `cli.py`: 통합 메뉴 및 직접 실행용 모드 alias
  - `common/`: 런타임 경로/유틸
  - `config.py`: 공통 설정(거래/수수료/거래소 API)
  - `overseas/`: 해외 현물+선물 헤지 진입/청산
  - `korea/exit/`: 김프 청산/Exit
  - `korea/redflag/`: 한국 거래소 레드플래그 진입 봇
- `tests/`: 오프라인 단위 테스트(실거래 없음)
- `runtime/`: 실행 중 생성되는 state/cache/logs (기본)

워크플로 매핑
-------------
- Korea entry (legacy `hedge-pilot` 흡수): `overseas_exchange_hedge.korea.redflag.app:main`
- Overseas unwind: `overseas_exchange_hedge.overseas.app:run_overseas_unwind`
- Overseas manual entry: `overseas_exchange_hedge.overseas.app:run_overseas_entry(entry_mode="manual")`
- Korea premium exit: `overseas_exchange_hedge.korea.exit.app:main` (`UnifiedExitManager`)
- Overseas auto entry (legacy `contango-hunter` 흡수): `overseas_exchange_hedge.overseas.app:run_overseas_entry(entry_mode="auto")`

런타임 파일(상태/캐시/로그)
--------------------------
- `overseas_exchange_hedge.common.paths`가 `runtime/` 아래에 아래 디렉토리를 보장한다.
  - `runtime/state/`: `positions.json`, `exit_state.json` 등
  - `runtime/cache/`: OKX/Bybit 상태 캐시 등
  - `runtime/logs/`: 로깅 출력
- 필요 시 `OEH_RUNTIME_DIR`로 위치 변경 가능.

해외 헤지 엔진(요약)
-------------------
- `overseas/exchange_manager.py`
  - `ExchangeManager`: ccxt 거래소 초기화, 심볼 로딩, 입출금 가능 여부(transferable) 판단.
- `overseas/price_analyzer.py`
  - `PriceAnalyzer`: 오더북/펀딩비 조회, 수수료 반영 스프레드 계산, 최적 조합 탐색.
- `overseas/trade_executor.py`
  - `TradeExecutor`: 1x 레버리지 강제, 주문/체결 폴링, spot/perp 실행 헬퍼.
- `overseas/position_tracker.py`
  - `PositionTracker`: 진입 기록/평단/잔여 수량 관리, 부분 청산을 위한 pair aggregation.

김프 Exit(요약)
--------------
- `korea/exit/korean_exchanges.py`
  - `KoreanExchangeManager`: 빗썸/업비트 연결 및 잔고/주문/가격 조회.
- `korea/exit/kimchi_premium.py`
  - `KimchiPremiumCalculator`: 환율 + 해외 가격 + 한국 호가를 이용해 김프 산출.
- `korea/exit/app.py`
  - `UnifiedExitManager`: 한국 현물 매도 체결에 맞춰 해외 선물 숏을 reduce-only로 청산.

레드플래그 봇(요약)
------------------
- `korea/redflag/app.py`
  - 사용자 입력 → 거래소 초기화 → `HedgeBot.run_cycle()` 루프.
- `korea/redflag/core/`, `managers/`, `exchanges/`
  - 프리미엄 계산, 주문 실행, 스테이지 타이머/포지션 관리 등을 역할별로 분리.

테스트
------
- 테스트는 네트워크/실거래를 강제하지 않도록 mock 기반으로 구성되어 있다.
- 실행:
  - `uv run pytest`
  - `uv run mypy src tests`
  - `uv run ruff check .`
