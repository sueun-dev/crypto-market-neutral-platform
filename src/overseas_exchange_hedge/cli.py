"""Unified CLI for market-neutral hedge workflows."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence

from .common.logging_utils import setup_logging

logger = logging.getLogger(__name__)

ModeHandler = Callable[[], None]

INTERACTIVE_CHOICES = {
    "1": "korea-entry",
    "2": "overseas-unwind",
    "3": "overseas-entry-manual",
    "4": "korea-exit",
    "5": "overseas-entry-auto",
}

MODE_ALIASES = {
    "korea-entry": "korea-entry",
    "redflag": "korea-entry",
    "step1": "korea-entry",
    "overseas-unwind": "overseas-unwind",
    "step2": "overseas-unwind",
    "overseas-entry-manual": "overseas-entry-manual",
    "manual": "overseas-entry-manual",
    "contango-manual": "overseas-entry-manual",
    "step3": "overseas-entry-manual",
    "korea-exit": "korea-exit",
    "exit": "korea-exit",
    "step4": "korea-exit",
    "overseas-entry-auto": "overseas-entry-auto",
    "auto": "overseas-entry-auto",
    "contango-auto": "overseas-entry-auto",
    "contango": "overseas-entry-auto",
    "step5": "overseas-entry-auto",
}


def _select_mode() -> str:
    logger.info("\n" + "=" * 60)
    logger.info("Market-Neutral Workflow Selection")
    logger.info("=" * 60)
    logger.info("1. Korea basis entry")
    logger.info("2. Overseas unwind (spot + perp)")
    logger.info("3. Overseas basis entry - manual venue selection")
    logger.info("4. Korea premium exit / position cleanup")
    logger.info("5. Overseas basis entry - auto venue discovery")
    logger.info("0. 종료")
    return input("\n모드 선택 (0-5) [5]: ").strip() or "5"


def _build_handlers() -> dict[str, ModeHandler]:
    return {
        "korea-entry": _run_step1_redflag_entry,
        "overseas-unwind": _run_step2_overseas_unwind,
        "overseas-entry-manual": _run_step3_overseas_manual_entry,
        "korea-exit": _run_step4_kimchi_exit,
        "overseas-entry-auto": _run_overseas_auto_entry,
    }


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="market-neutral",
        description="Unified market-neutral hedge workflows",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        help="Direct mode: korea-entry, overseas-unwind, overseas-entry-manual, korea-exit, overseas-entry-auto",
    )
    return parser.parse_args(list(argv))


def _dispatch_mode(mode: str, handlers: dict[str, ModeHandler]) -> None:
    handler = handlers.get(mode)
    if not handler:
        logger.error("❌ 올바르지 않은 선택입니다.")
        raise SystemExit(2)
    handler()


def main(argv: Sequence[str] | None = None) -> None:
    setup_logging()
    handlers = _build_handlers()
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.mode:
        if args.mode in {"0", "q", "quit"}:
            return
        canonical = MODE_ALIASES.get(args.mode)
        if not canonical:
            logger.error("❌ 지원하지 않는 모드입니다: %s", args.mode)
            raise SystemExit(2)
        _dispatch_mode(canonical, handlers)
        return

    choice = _select_mode()
    if choice in {"0", "q", "quit", "exit"}:
        return
    canonical = INTERACTIVE_CHOICES.get(choice) or MODE_ALIASES.get(choice)
    if not canonical:
        logger.error("❌ 올바르지 않은 선택입니다. (0-5)")
        return
    _dispatch_mode(canonical, handlers)


def market_neutral_main() -> None:
    main([])


def market_neutral_korea_entry() -> None:
    main(["korea-entry"])


def market_neutral_overseas_unwind() -> None:
    main(["overseas-unwind"])


def market_neutral_overseas_entry_auto() -> None:
    main(["overseas-entry-auto"])


def market_neutral_overseas_entry_manual() -> None:
    main(["overseas-entry-manual"])


def market_neutral_korea_exit() -> None:
    main(["korea-exit"])


def _run_overseas_auto_entry() -> None:
    from .overseas.app import run_overseas_entry

    run_overseas_entry(entry_mode="auto")


def _run_step3_overseas_manual_entry() -> None:
    from .overseas.app import run_overseas_entry

    run_overseas_entry(entry_mode="manual")


def _run_step2_overseas_unwind() -> None:
    from .overseas.app import run_overseas_unwind

    run_overseas_unwind()


def _run_step4_kimchi_exit() -> None:
    from .korea.exit.app import main as run_exit

    run_exit()


def _run_step1_redflag_entry() -> None:
    from .korea.redflag.app import main as run_redflag

    run_redflag()
