import os
import sys
import time
import logging
from typing import List, Tuple
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 프로젝트 모듈 import
from src.config import settings
from src.utils import setup_logging
from src.core import HedgeBot
from src.exchanges.upbit import UpbitExchange
from src.exchanges.bithumb import BithumbExchange
from src.exchanges.gateio import GateIOExchange

# 로깅 설정
setup_logging()
logger = logging.getLogger(__name__)


class RedflagHedgeBot:
    """레드플래그 헤징 봇 메인 클래스"""
    
    # 완료
    def __init__(self):
        self.bot = None
        self.korean_exchange = None
        self.futures_exchange = None
    
    # 완료
    def get_user_input(self) -> Tuple[List[str], str, str]:
        
        symbols_input = input("거래할 코인 심볼 (쉼표로 구분, 예: XRP,ETH,BTC): ").strip().upper()
        symbols = [s.strip() for s in symbols_input.split(',') if s.strip()]
        
        logger.info("한국 거래소 선택: 1. Upbit, 2. Bithumb")
        while True:
            choice = input("선택 (1-2): ").strip()
            if choice == '1':
                korean_exchange = 'upbit'
                break
            elif choice == '2':
                korean_exchange = 'bithumb'
                break
            logger.warning("1 또는 2를 입력해주세요.")
        
        # 선물 거래소는 GateIO만 지원
        futures_exchange = 'gateio'
        logger.info("선물 거래소: GateIO (현재는 1개만 지원)")
        
        return symbols, korean_exchange, futures_exchange
    
    # 완료
    def initialize_exchanges(self, korean_name: str, futures_name: str) -> bool:
        """거래소 초기화"""
        try:
            # 한국 거래소 API 키 가져오기
            korean_key = os.getenv(f'{korean_name.upper()}_API_KEY')
            korean_secret = os.getenv(f'{korean_name.upper()}_API_SECRET')
            
            # 선물 거래소 API 키 가져오기
            futures_key = os.getenv(f'{futures_name.upper()}_API_KEY')
            futures_secret = os.getenv(f'{futures_name.upper()}_API_SECRET')
            
            if not all([korean_key, korean_secret, futures_key, futures_secret]):
                logger.error("API 인증 정보가 .env 파일에 없습니다.")
                logger.error(f"필요한 환경변수:")
                logger.error(f"{korean_name.upper()}_API_KEY")
                logger.error(f"{korean_name.upper()}_API_SECRET")
                logger.error(f"{futures_name.upper()}_API_KEY")
                logger.error(f"{futures_name.upper()}_API_SECRET")
                return False
            
            # 한국 거래소 초기화
            if korean_name == 'upbit':
                self.korean_exchange = UpbitExchange(korean_key, korean_secret)
            else:  # korean_name == 'bithumb' (already validated in get_user_input)
                self.korean_exchange = BithumbExchange(korean_key, korean_secret)
            
            # 선물 거래소 초기화
            if futures_name == 'gateio':
                self.futures_exchange = GateIOExchange({
                    'apiKey': futures_key,
                    'secret': futures_secret
                })
            # 나중에 다른 선물 거래소 추가 시 여기에 elif 추가
            else:
                logger.error(f"지원하지 않는 선물 거래소: {futures_name}")
                return False
            
            logger.info(f"거래소 초기화 완료: {korean_name} + {futures_name}")
            return True
            
        except Exception as e:
            logger.error(f"거래소 초기화 실패: {e}")
            return False
    
    # 완료
    def run(self):
        """봇 실행"""
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
        
        logger.info(f"거래 준비 완료 - 심볼: {', '.join(self.bot.symbols)}, 한국 거래소: {korean_exchange}, 선물 거래소: {futures_exchange}")
        logger.info(f"설정 - 최대 포지션: ${settings.MAX_POSITION_USD}, 포지션 증가 단위: ${settings.POSITION_INCREMENT_USD}, 타이머: {settings.STAGE_TIMER_MINUTES}분, 확인 간격: {settings.MAIN_LOOP_INTERVAL}초")
        
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


if __name__ == "__main__":
    bot = RedflagHedgeBot()
    bot.run()