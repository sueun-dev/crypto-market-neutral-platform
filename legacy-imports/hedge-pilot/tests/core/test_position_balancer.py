"""
Comprehensive test suite for position_balancer.py
Tests all functionality with mocks and verifies correct behavior
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
import logging

# Import the module to test
from src.core.position_balancer import PositionBalancer, PositionBalance
from src.config import settings

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestPositionBalancer:
    """Test suite for PositionBalancer class"""
    
    @pytest.fixture
    def mock_exchanges(self):
        """Create mock exchange objects"""
        korean_exchange = Mock()
        korean_exchange.exchange_id = 'upbit'
        
        futures_exchange = Mock()
        futures_exchange.exchange_id = 'gateio'
        
        return korean_exchange, futures_exchange
    
    @pytest.fixture
    def mock_managers(self):
        """Create mock manager objects"""
        position_manager = Mock()
        position_manager.positions = {}
        
        order_executor = Mock()
        
        return position_manager, order_executor
    
    @pytest.fixture
    def balancer(self, mock_exchanges, mock_managers):
        """Create PositionBalancer instance with mocks"""
        korean_exchange, futures_exchange = mock_exchanges
        position_manager, order_executor = mock_managers
        
        return PositionBalancer(
            position_manager,
            order_executor,
            korean_exchange,
            futures_exchange
        )
    
    def test_init(self, balancer):
        """Test PositionBalancer initialization"""
        assert balancer.max_gap_usd == settings.MAX_POSITION_GAP_USD
        assert balancer.rebalance_threshold == settings.REBALANCE_THRESHOLD_USD
        assert balancer.position_manager is not None
        assert balancer.order_executor is not None
        assert balancer.korean_exchange is not None
        assert balancer.futures_exchange is not None
    
    def test_check_position_balance_balanced(self, balancer):
        """Test checking balanced positions"""
        # Mock spot position info (quantity, value)
        balancer._get_spot_position_info = Mock(return_value=(0.1, 1000.0))
        
        # Mock futures position info (quantity, value)
        balancer._get_futures_position_info = Mock(return_value=(0.1005, 1005.0))
        
        # Check balance
        result = balancer.check_position_balance('BTC')
        
        assert result is not None
        assert result.symbol == 'BTC'
        assert result.spot_quantity == 0.1
        assert result.futures_quantity == 0.1005
        assert result.spot_value_usd == 1000.0
        assert result.futures_value_usd == 1005.0
        assert result.quantity_gap < 0.01  # Small gap in quantity
        assert result.gap_percentage < 1.0  # Less than 1%
        assert result.is_balanced == True
        assert result.needs_rebalancing == False
    
    def test_check_position_balance_unbalanced(self, balancer):
        """Test checking unbalanced positions"""
        # Mock spot position info (quantity, value)
        balancer._get_spot_position_info = Mock(return_value=(100.0, 1000.0))
        
        # Mock futures position info (quantity, value) - significant gap
        balancer._get_futures_position_info = Mock(return_value=(80.0, 1020.0))
        
        # Check balance
        result = balancer.check_position_balance('XRP')
        
        assert result is not None
        assert result.symbol == 'XRP'
        assert result.spot_quantity == 100.0
        assert result.futures_quantity == 80.0
        assert result.spot_value_usd == 1000.0
        assert result.futures_value_usd == 1020.0
        assert result.quantity_gap == 20.0  # 20 XRP gap
        assert result.gap_percentage == 20.0  # 20% gap in quantity
        assert result.is_balanced == False
        assert result.needs_rebalancing == True
    
    def test_check_position_balance_exception(self, balancer):
        """Test check_position_balance with exception"""
        # Mock exception
        balancer._get_spot_position_info = Mock(side_effect=Exception("Test error"))
        
        # Should return None on exception
        result = balancer.check_position_balance('ETH')
        assert result is None
    
    def test_get_spot_position_value_success(self, balancer, mock_exchanges):
        """Test getting spot position value successfully"""
        korean_exchange, _ = mock_exchanges
        
        # Mock balance
        korean_exchange.fetch_balance.return_value = {
            'free': {'XRP': 100.0}
        }
        
        # Mock ticker
        korean_exchange.get_ticker.side_effect = [
            {'bid': 1500.0, 'ask': 1510.0},  # XRP/KRW
            {'bid': 1370.0, 'ask': 1380.0}   # USDT/KRW
        ]
        
        # Get spot value
        value = balancer._get_spot_position_value('XRP')
        
        # 100 XRP * 1500 KRW/XRP / 1380 KRW/USDT = ~108.7 USD
        assert value == pytest.approx(108.7, rel=0.01)
    
    def test_get_spot_position_value_no_balance(self, balancer, mock_exchanges):
        """Test getting spot position value with no balance"""
        korean_exchange, _ = mock_exchanges
        
        # Mock empty balance
        korean_exchange.fetch_balance.return_value = {
            'free': {}
        }
        
        # Get spot value
        value = balancer._get_spot_position_value('BTC')
        assert value == 0.0
    
    def test_get_futures_position_value_success(self, balancer, mock_exchanges):
        """Test getting futures position value successfully"""
        _, futures_exchange = mock_exchanges
        
        # Mock positions with Gate.io format
        futures_exchange.get_positions.return_value = [
            {
                'contract': 'XRP_USDT',
                'symbol': 'XRP/USDT:USDT',
                'side': 'short',
                'value': '500.5',  # USD value
                'size': -450,  # Negative for short
                'mark_price': '1.11'
            }
        ]
        
        # Get futures value
        value = balancer._get_futures_position_value('XRP')
        assert value == 500.5
    
    def test_get_futures_position_value_no_position(self, balancer, mock_exchanges):
        """Test getting futures position value with no position"""
        _, futures_exchange = mock_exchanges
        
        # Mock empty positions
        futures_exchange.get_positions.return_value = []
        
        # Get futures value
        value = balancer._get_futures_position_value('BTC')
        assert value == 0.0
    
    def test_get_futures_position_value_fallback_calculation(self, balancer, mock_exchanges):
        """Test futures value calculation fallback"""
        _, futures_exchange = mock_exchanges
        
        # Mock position without 'value' field
        futures_exchange.get_positions.return_value = [
            {
                'contract': 'BTC_USDT',
                'symbol': 'BTC/USDT:USDT',
                'side': 'short',
                'size': -10,
                'mark_price': '70000'
            }
        ]
        
        # Get futures value (should calculate: 10 * 70000 = 700000)
        value = balancer._get_futures_position_value('BTC')
        assert value == 700000.0
    
    def test_rebalance_position_no_rebalance_needed(self, balancer):
        """Test rebalance when no rebalancing is needed"""
        # Mock balanced positions
        mock_balance = PositionBalance(
            symbol='XRP',
            spot_quantity=100.0,
            futures_quantity=100.5,
            spot_value_usd=1000.0,
            futures_value_usd=1005.0,
            quantity_gap=0.5,
            gap_percentage=0.5,
            is_balanced=True,
            needs_rebalancing=False,
            timestamp=datetime.now()
        )
        
        balancer.check_position_balance = Mock(return_value=mock_balance)
        
        # Should return True without doing anything
        result = balancer.rebalance_position('XRP')
        assert result == True
    
    def test_rebalance_position_add_futures(self, balancer):
        """Test rebalancing by adding futures position"""
        # Mock unbalanced positions (spot > futures)
        mock_balance = PositionBalance(
            symbol='XRP',
            spot_quantity=102.0,
            futures_quantity=100.0,
            spot_value_usd=1020.0,
            futures_value_usd=1000.0,
            quantity_gap=2.0,
            gap_percentage=2.0,
            is_balanced=False,
            needs_rebalancing=True,
            timestamp=datetime.now()
        )
        
        balancer.check_position_balance = Mock(return_value=mock_balance)
        balancer._add_futures_short = Mock(return_value=True)
        
        # Rebalance
        result = balancer.rebalance_position('XRP')
        
        assert result == True
        balancer._add_futures_short.assert_called_once_with('XRP', 20.0)
    
    def test_rebalance_position_add_spot(self, balancer):
        """Test rebalancing by adding spot position"""
        # Mock unbalanced positions (futures > spot)
        mock_balance = PositionBalance(
            symbol='XRP',
            spot_quantity=100.0,
            futures_quantity=102.0,
            spot_value_usd=1000.0,
            futures_value_usd=1020.0,
            quantity_gap=2.0,
            gap_percentage=2.0,
            is_balanced=False,
            needs_rebalancing=True,
            timestamp=datetime.now()
        )
        
        balancer.check_position_balance = Mock(return_value=mock_balance)
        balancer._add_spot_position = Mock(return_value=True)
        
        # Rebalance
        result = balancer.rebalance_position('XRP')
        
        assert result == True
        balancer._add_spot_position.assert_called_once_with('XRP', 20.0)
    
    def test_add_futures_short_success(self, balancer, mock_exchanges):
        """Test adding futures short position successfully"""
        _, futures_exchange = mock_exchanges
        
        # Mock ticker
        futures_exchange.get_ticker.return_value = {
            'bid': 1.10,
            'ask': 1.11
        }
        
        # Mock successful order
        futures_exchange.create_market_order.return_value = {
            'id': '12345',
            'status': 'filled'
        }
        
        # Add futures short
        result = balancer._add_futures_short('XRP', 100.0)
        
        assert result == True
        futures_exchange.create_market_order.assert_called_once()
        
        # Check order parameters
        call_args = futures_exchange.create_market_order.call_args
        assert call_args[1]['symbol'] == 'XRP/USDT:USDT'
        assert call_args[1]['side'] == 'sell'
        assert call_args[1]['amount'] == pytest.approx(90.9, rel=0.01)  # 100/1.10
    
    def test_add_futures_short_amount_too_small(self, balancer):
        """Test adding futures short with amount too small"""
        result = balancer._add_futures_short('XRP', 5.0)  # Less than $10
        assert result == True  # Returns True but doesn't place order
    
    def test_add_spot_position_success(self, balancer, mock_exchanges):
        """Test adding spot position successfully"""
        korean_exchange, _ = mock_exchanges
        korean_exchange.exchange_id = 'upbit'
        
        # Mock tickers
        korean_exchange.get_ticker.side_effect = [
            {'bid': 1370.0, 'ask': 1380.0},  # USDT/KRW
            {'bid': 1490.0, 'ask': 1500.0}   # XRP/KRW
        ]
        
        # Mock successful order
        korean_exchange.create_market_order.return_value = {
            'id': '67890',
            'status': 'filled'
        }
        
        # Add spot position
        result = balancer._add_spot_position('XRP', 100.0)
        
        assert result == True
        korean_exchange.create_market_order.assert_called_once()
        
        # Check order parameters (should be KRW amount for Upbit)
        call_args = korean_exchange.create_market_order.call_args
        assert call_args[1]['symbol'] == 'XRP/KRW'
        assert call_args[1]['side'] == 'buy'
        assert call_args[1]['amount'] == 137000.0  # 100 * 1370
    
    def test_check_all_positions(self, balancer, mock_managers):
        """Test checking all positions"""
        position_manager, _ = mock_managers
        
        # Mock positions
        position_manager.positions = {
            'XRP': Mock(),
            'BTC': Mock()
        }
        
        # Mock balance checks
        mock_balances = [
            PositionBalance(
                symbol='XRP',
                spot_quantity=1000.0,
                futures_quantity=1005.0,
                spot_value_usd=1000.0,
                futures_value_usd=1005.0,
                quantity_gap=5.0,
                gap_percentage=0.5,
                is_balanced=True,
                needs_rebalancing=False,
                timestamp=datetime.now()
            ),
            PositionBalance(
                symbol='BTC',
                spot_quantity=1.0,
                futures_quantity=1.0004,
                spot_value_usd=50000.0,
                futures_value_usd=50020.0,
                quantity_gap=0.0004,
                gap_percentage=0.04,
                is_balanced=False,
                needs_rebalancing=True,
                timestamp=datetime.now()
            )
        ]
        
        balancer.check_position_balance = Mock(side_effect=mock_balances)
        
        # Check all positions
        result = balancer.check_all_positions()
        
        assert len(result) == 2
        assert 'XRP' in result
        assert 'BTC' in result
        assert result['XRP'].is_balanced == True
        assert result['BTC'].is_balanced == False
    
    @patch('time.sleep')
    def test_balance_after_close_balanced(self, mock_sleep, balancer):
        """Test balance after close when already balanced"""
        # Mock balanced position
        mock_balance = PositionBalance(
            symbol='XRP',
            spot_quantity=200.0,
            futures_quantity=210.0,
            spot_value_usd=100.0,
            futures_value_usd=105.0,
            quantity_gap=10.0,
            gap_percentage=5.0,
            is_balanced=True,
            needs_rebalancing=False,
            timestamp=datetime.now()
        )
        
        balancer.check_position_balance = Mock(return_value=mock_balance)
        
        # Balance after close
        result = balancer.balance_after_close('XRP')
        
        assert result == True
        mock_sleep.assert_called_once_with(2)
    
    @patch('time.sleep')
    def test_balance_after_close_excess_spot(self, mock_sleep, balancer):
        """Test balance after close with excess spot"""
        # Mock unbalanced position (spot > futures)
        mock_balance = PositionBalance(
            symbol='XRP',
            spot_quantity=260.0,
            futures_quantity=200.0,
            spot_value_usd=130.0,
            futures_value_usd=100.0,
            quantity_gap=60.0,
            gap_percentage=30.0,
            is_balanced=False,
            needs_rebalancing=True,
            timestamp=datetime.now()
        )
        
        # Mock balanced after adjustment
        mock_balance_after = PositionBalance(
            symbol='XRP',
            spot_quantity=210.0,
            futures_quantity=200.0,
            spot_value_usd=105.0,
            futures_value_usd=100.0,
            quantity_gap=10.0,
            gap_percentage=5.0,
            is_balanced=True,
            needs_rebalancing=False,
            timestamp=datetime.now()
        )
        
        balancer.check_position_balance = Mock(side_effect=[mock_balance, mock_balance_after])
        balancer._close_excess_spot = Mock(return_value=True)
        
        # Balance after close
        result = balancer.balance_after_close('XRP')
        
        assert result == True
        balancer._close_excess_spot.assert_called_once_with('XRP', 30.0)
        assert mock_sleep.call_count == 2  # Called twice
    
    @patch('time.sleep')
    def test_balance_after_close_excess_futures(self, mock_sleep, balancer):
        """Test balance after close with excess futures"""
        # Mock unbalanced position (futures > spot)
        mock_balance = PositionBalance(
            symbol='XRP',
            spot_quantity=200.0,
            futures_quantity=260.0,
            spot_value_usd=100.0,
            futures_value_usd=130.0,
            quantity_gap=60.0,
            gap_percentage=30.0,
            is_balanced=False,
            needs_rebalancing=True,
            timestamp=datetime.now()
        )
        
        # Mock balanced after adjustment
        mock_balance_after = PositionBalance(
            symbol='XRP',
            spot_quantity=200.0,
            futures_quantity=210.0,
            spot_value_usd=100.0,
            futures_value_usd=105.0,
            quantity_gap=10.0,
            gap_percentage=5.0,
            is_balanced=True,
            needs_rebalancing=False,
            timestamp=datetime.now()
        )
        
        balancer.check_position_balance = Mock(side_effect=[mock_balance, mock_balance_after])
        balancer._close_excess_futures = Mock(return_value=True)
        
        # Balance after close
        result = balancer.balance_after_close('XRP')
        
        assert result == True
        balancer._close_excess_futures.assert_called_once_with('XRP', 30.0)
        assert mock_sleep.call_count == 2
    
    def test_close_excess_spot_success(self, balancer, mock_exchanges):
        """Test closing excess spot position"""
        korean_exchange, _ = mock_exchanges
        korean_exchange.exchange_id = 'bithumb'
        
        # Mock tickers
        korean_exchange.get_ticker.side_effect = [
            {'bid': 1490.0, 'ask': 1500.0},  # XRP/KRW
            {'bid': 1370.0, 'ask': 1380.0}   # USDT/KRW
        ]
        
        # Mock successful order
        korean_exchange.create_market_order.return_value = {
            'id': 'sell123',
            'status': 'filled'
        }
        
        # Close excess spot
        result = balancer._close_excess_spot('XRP', 50.0)
        
        assert result == True
        korean_exchange.create_market_order.assert_called_once()
        
        # Check order parameters
        call_args = korean_exchange.create_market_order.call_args
        assert call_args[1]['symbol'] == 'XRP/KRW'
        assert call_args[1]['side'] == 'sell'
        # Quantity calculation: 50 USD / (1490 KRW / 1380 KRW/USD) ≈ 46.3
        assert call_args[1]['amount'] == pytest.approx(46.3, rel=0.01)
    
    def test_close_excess_futures_success(self, balancer, mock_exchanges):
        """Test closing excess futures position"""
        _, futures_exchange = mock_exchanges
        
        # Mock ticker
        futures_exchange.get_ticker.return_value = {
            'bid': 1.10,
            'ask': 1.11
        }
        
        # Mock successful order
        futures_exchange.create_market_order.return_value = {
            'id': 'buy456',
            'status': 'filled'
        }
        
        # Close excess futures
        result = balancer._close_excess_futures('XRP', 50.0)
        
        assert result == True
        futures_exchange.create_market_order.assert_called_once()
        
        # Check order parameters
        call_args = futures_exchange.create_market_order.call_args
        assert call_args[1]['symbol'] == 'XRP/USDT:USDT'
        assert call_args[1]['side'] == 'buy'
        assert call_args[1]['amount'] == pytest.approx(45.05, rel=0.01)  # 50/1.11
        assert call_args[1]['params'] == {'reduce_only': True}
    
    def test_close_excess_spot_bithumb_rounding(self, balancer, mock_exchanges):
        """Test Bithumb 4-digit rounding for spot orders"""
        korean_exchange, _ = mock_exchanges
        korean_exchange.exchange_id = 'bithumb'
        
        # Mock tickers
        korean_exchange.get_ticker.side_effect = [
            {'bid': 1490.123456, 'ask': 1500.0},  # XRP/KRW
            {'bid': 1370.0, 'ask': 1380.789}      # USDT/KRW
        ]
        
        korean_exchange.create_market_order.return_value = {'id': 'test', 'status': 'filled'}
        
        # Close excess spot
        result = balancer._close_excess_spot('XRP', 50.0)
        
        # Check that amount is rounded to 4 decimal places for Bithumb
        call_args = korean_exchange.create_market_order.call_args
        amount = call_args[1]['amount']
        
        # Check it's rounded to 4 decimal places
        assert round(amount, 4) == amount
        assert len(str(amount).split('.')[-1]) <= 4 if '.' in str(amount) else True


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, '-v', '--tb=short'])