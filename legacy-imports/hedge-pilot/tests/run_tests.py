#!/usr/bin/env python3
"""
테스트 실행 스크립트
"""
import os
import sys
import unittest
import argparse
from datetime import datetime

# 프로젝트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_all_tests(verbosity=2):
    """모든 테스트 실행"""
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(os.path.abspath(__file__))
    suite = loader.discover(start_dir, pattern='test_*.py')
    
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    return result.wasSuccessful()


def run_specific_test(test_module, test_class=None, test_method=None, verbosity=2):
    """특정 테스트 실행"""
    loader = unittest.TestLoader()
    
    if test_method and test_class:
        suite = loader.loadTestsFromName(f'{test_module}.{test_class}.{test_method}')
    elif test_class:
        suite = loader.loadTestsFromName(f'{test_module}.{test_class}')
    else:
        suite = loader.loadTestsFromName(test_module)
    
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    return result.wasSuccessful()


def run_live_tests(verbosity=2):
    """실제 API를 사용하는 라이브 테스트 실행"""
    print("\n" + "="*70)
    print("라이브 테스트 시작 (실제 API 사용)")
    print("="*70 + "\n")
    
    # 환경 변수 확인
    required_vars = ['BITHUMB_API_KEY', 'BITHUMB_API_SECRET']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ 필수 환경 변수가 설정되지 않았습니다: {', '.join(missing_vars)}")
        print("\n.env 파일에 다음 변수들을 설정해주세요:")
        for var in missing_vars:
            print(f"  {var}=your_{var.lower()}")
        return False
    
    # LIVE_TEST 환경 변수 설정
    os.environ['LIVE_TEST'] = 'true'
    
    # 테스트 실행
    return run_all_tests(verbosity)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='Bithumb 거래소 테스트 실행')
    parser.add_argument('--live', action='store_true', help='실제 API를 사용하는 라이브 테스트 실행')
    parser.add_argument('--module', type=str, help='특정 테스트 모듈 실행 (예: test_bithumb)')
    parser.add_argument('--class', type=str, help='특정 테스트 클래스 실행')
    parser.add_argument('--method', type=str, help='특정 테스트 메서드 실행')
    parser.add_argument('-v', '--verbosity', type=int, default=2, choices=[0, 1, 2], 
                       help='출력 상세도 (0: 조용함, 1: 보통, 2: 상세)')
    parser.add_argument('--no-trade', action='store_true', help='거래 테스트 제외 (읽기 전용 테스트만 실행)')
    
    args = parser.parse_args()
    
    print(f"\n🧪 테스트 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 70)
    
    success = False
    
    try:
        if args.live:
            success = run_live_tests(args.verbosity)
        elif args.module:
            success = run_specific_test(args.module, args.class, args.method, args.verbosity)
        else:
            success = run_all_tests(args.verbosity)
    except Exception as e:
        print(f"\n❌ 테스트 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
    
    print("-" * 70)
    if success:
        print("✅ 모든 테스트 통과!")
    else:
        print("❌ 일부 테스트 실패")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())