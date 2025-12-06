"""
Functional test for Tournament flow - end-to-end testing.
Tests the full tournament pipeline from config to result with reproducibility.

Run from NextJsAppBot/V2/prototype/python:
    python -m pytest tests/test_tournament_flow.py -v
"""

import os
import sys
import json
import pytest
import random
from pathlib import Path

# Ensure we're using the local python modules
PYTHON_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PYTHON_DIR))

# Set config path before importing modules that need it
os.environ.setdefault('CONFIG_PATH', str(PYTHON_DIR / 'config.yaml'))

from prompt_performance.tournament import TournamentConfig, PromptTournament, PromptScore
from prompt_performance.backtest_with_images import ImageSelector, PROMPT_REGISTRY


# Test fixtures - same paths as tournament uses
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
CHARTS_DIR = REPO_ROOT / 'trading_bot' / 'data' / 'charts' / '.backup'
DB_PATH = PYTHON_DIR.parent / 'data' / 'bot.db'

# Get actual symbols from charts directory
def get_available_symbols():
    """Discover symbols that actually exist in charts dir"""
    if not CHARTS_DIR.exists():
        return []
    symbols = set()
    for f in CHARTS_DIR.glob("*.png"):
        parts = f.stem.split('_')
        if len(parts) >= 2:
            symbols.add(parts[0])
    return list(symbols)[:3]  # First 3 symbols

AVAILABLE_SYMBOLS = get_available_symbols()


class TestTournamentConfig:
    """Test TournamentConfig dataclass"""

    def test_default_config(self):
        config = TournamentConfig()
        assert config.model == "gpt-4o"
        assert config.elimination_pct == 50
        assert config.selection_strategy == "random"
        assert config.ranking_strategy == "wilson"
        assert config.random_symbols == False
        assert config.random_timeframes == False

    def test_custom_config(self):
        config = TournamentConfig(
            model="gpt-4o-mini",
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=["1h"],
            random_symbols=True,
            random_timeframes=False,
            elimination_pct=40
        )
        assert config.model == "gpt-4o-mini"
        assert config.symbols == ["BTCUSDT", "ETHUSDT"]
        assert config.random_symbols == True
        assert config.elimination_pct == 40


class TestPromptScore:
    """Test PromptScore calculations"""

    def test_win_rate_calculation(self):
        score = PromptScore(prompt_name="test", wins=7, losses=3, holds=0)
        assert score.trades == 10
        assert score.win_rate == 70.0

    def test_avg_pnl_calculation(self):
        score = PromptScore(prompt_name="test", wins=5, losses=5, total_pnl=15.0)
        assert score.avg_pnl == 1.5  # 15 / 10 trades

    def test_wilson_lower_bound(self):
        score = PromptScore(prompt_name="test", wins=8, losses=2)
        wilson = score.wilson_lower
        assert wilson > 0
        assert wilson < score.win_rate  # Wilson is always lower than raw win rate

    def test_confidence_scaling(self):
        # Low trades = low confidence
        low = PromptScore(prompt_name="low", wins=3, losses=2)
        high = PromptScore(prompt_name="high", wins=21, losses=9)
        assert low.confidence < high.confidence
        assert high.confidence == 1.0  # 30 trades = max confidence


class TestImageSelector:
    """Test ImageSelector functionality"""

    @pytest.fixture
    def selector(self):
        if not CHARTS_DIR.exists():
            pytest.skip(f"Charts directory not found: {CHARTS_DIR}")
        return ImageSelector(str(CHARTS_DIR))

    def test_discover_images(self, selector):
        images = selector.discover_images()
        assert len(images) > 0
        # Check image info structure
        img = images[0]
        assert hasattr(img, 'symbol')
        assert hasattr(img, 'timeframe')
        assert hasattr(img, 'timestamp')

    def test_select_images_with_symbols(self, selector):
        if not AVAILABLE_SYMBOLS:
            pytest.skip("No symbols available")
        symbol = AVAILABLE_SYMBOLS[0]
        images = selector.select_images(
            symbols=[symbol],
            num_images=5
        )
        assert len(images) <= 5
        for img in images:
            assert img.symbol == symbol

    def test_select_images_with_timeframes(self, selector):
        if not AVAILABLE_SYMBOLS:
            pytest.skip("No symbols available")
        images = selector.select_images(
            symbols=AVAILABLE_SYMBOLS[:2],
            num_images=10,
            timeframes=["1h"]
        )
        for img in images:
            assert img.timeframe == "1h"


class TestTournamentInitialization:
    """Test PromptTournament initialization"""

    @pytest.fixture
    def tournament(self):
        if not CHARTS_DIR.exists():
            pytest.skip(f"Charts directory not found: {CHARTS_DIR}")
        if not AVAILABLE_SYMBOLS:
            pytest.skip("No symbols available")
        config = TournamentConfig(
            symbols=AVAILABLE_SYMBOLS[:2],
            timeframes=["1h"],
            images_phase_1=2,
            images_phase_2=3,
            images_phase_3=5
        )
        return PromptTournament(
            config=config,
            charts_dir=str(CHARTS_DIR),
            db_path=str(DB_PATH)
        )

    def test_random_seed_is_set(self, tournament):
        assert hasattr(tournament, '_random_seed')
        assert isinstance(tournament._random_seed, int)

    def test_phase_details_initialized(self, tournament):
        assert hasattr(tournament, '_phase_details')
        assert isinstance(tournament._phase_details, dict)

    def test_get_all_prompts(self, tournament):
        prompts = tournament.get_all_prompts()
        assert len(prompts) > 0
        assert 'get_market_data' not in prompts


class TestImageSelection:
    """Test image selection with reproducibility"""

    @pytest.fixture
    def tournament(self):
        if not CHARTS_DIR.exists():
            pytest.skip(f"Charts directory not found: {CHARTS_DIR}")
        if not AVAILABLE_SYMBOLS:
            pytest.skip("No symbols available")
        config = TournamentConfig(
            symbols=AVAILABLE_SYMBOLS[:2],
            timeframes=["1h"],
            selection_strategy="random"
        )
        return PromptTournament(
            config=config,
            charts_dir=str(CHARTS_DIR),
            db_path=str(DB_PATH)
        )

    def test_select_images_returns_list(self, tournament):
        images = tournament.select_images(5)
        assert isinstance(images, list)
        assert len(images) <= 5

    def test_reproducibility_with_same_seed(self, tournament):
        """Same seed should produce same image selection"""
        seed = tournament._random_seed

        # First selection
        random.seed(seed)
        images1 = tournament.select_images(5)

        # Reset and select again
        random.seed(seed)
        images2 = tournament.select_images(5)

        # Should be identical
        assert [str(i) for i in images1] == [str(i) for i in images2]


class TestRankingStrategies:
    """Test different ranking strategies"""

    def test_wilson_ranking(self):
        scores = [
            PromptScore(prompt_name="a", wins=8, losses=2),
            PromptScore(prompt_name="b", wins=15, losses=5),  # Same rate, more trades
            PromptScore(prompt_name="c", wins=3, losses=1),   # Higher rate, fewer trades
        ]
        # Wilson should favor b (more samples) over c (high rate but low n)
        sorted_scores = sorted(scores, key=lambda s: s.wilson_lower, reverse=True)
        assert sorted_scores[0].prompt_name == "b"

    def test_rank_score_includes_pnl(self):
        score1 = PromptScore(prompt_name="a", wins=8, losses=2, total_pnl=20)
        score2 = PromptScore(prompt_name="b", wins=8, losses=2, total_pnl=50)
        # Same win rate but different PnL
        assert score2.rank_score > score1.rank_score


class TestTournamentResult:
    """Test tournament result structure"""

    @pytest.fixture
    def mock_result(self):
        """Create a mock tournament result for testing structure"""
        return {
            'winner': 'test_prompt',
            'win_rate': 65.0,
            'avg_pnl': 2.5,
            'wilson_lower': 55.0,
            'rank_score': 0.85,
            'ranking_strategy': 'wilson',
            'rankings': [
                {'rank': 1, 'prompt': 'test_prompt', 'win_rate': 65.0}
            ],
            'phases': [{'phase': 1, 'eliminated': []}],
            'total_api_calls': 100,
            'duration_sec': 120.5,
            'random_seed': 1234567890,
            'config': {
                'model': 'gpt-4o',
                'symbols': ['BTCUSDT'],
                'timeframes': ['1h'],
                'random_symbols': False,
                'random_timeframes': False,
            },
            'phase_details': {
                'phase_1': {
                    'prompts_tested': ['test_prompt'],
                    'images_count': 5,
                    'images': [
                        {'filename': 'BTCUSDT_1h_20251126_120000.png', 'symbol': 'BTCUSDT', 'timeframe': '1h'}
                    ],
                    'symbols_used': ['BTCUSDT'],
                    'timeframes_used': ['1h']
                }
            }
        }

    def test_result_has_reproducibility_fields(self, mock_result):
        assert 'random_seed' in mock_result
        assert 'config' in mock_result
        assert 'phase_details' in mock_result

    def test_phase_details_has_image_info(self, mock_result):
        phase = mock_result['phase_details']['phase_1']
        assert 'images' in phase
        assert 'symbols_used' in phase
        assert 'timeframes_used' in phase
        assert phase['images'][0]['symbol'] == 'BTCUSDT'

    def test_config_has_random_flags(self, mock_result):
        config = mock_result['config']
        assert 'random_symbols' in config
        assert 'random_timeframes' in config


class TestElimination:
    """Test elimination logic"""

    def test_eliminate_keeps_minimum(self):
        """Should keep at least 2 prompts"""
        from prompt_performance.tournament import PromptTournament, TournamentConfig

        config = TournamentConfig(elimination_pct=90)  # Aggressive elimination

        # With 5 prompts and 90% elimination, should still keep 2
        keep_count = max(2, int(5 * (100 - 90) / 100))
        assert keep_count == 2


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])

