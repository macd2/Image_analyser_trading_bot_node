"""
StrategyFactory - Factory for creating analysis strategies with instance-specific config.

Loads strategy name and config from database, then instantiates
the appropriate strategy class.
"""

import json
import logging
from typing import Optional, Type, Dict, Any

logger = logging.getLogger(__name__)


class StrategyFactory:
    """
    Factory for creating analysis strategies.
    
    Loads strategy name and config from database, then instantiates
    the appropriate strategy class with instance-specific settings.
    """
    
    # Registry of available strategies
    STRATEGIES: Dict[str, Type] = {}
    
    @classmethod
    def register_strategy(cls, name: str, strategy_class: Type) -> None:
        """
        Register a strategy.
        
        Args:
            name: Strategy name (e.g., "prompt", "alex", "ml")
            strategy_class: Strategy class (must extend BaseAnalysisModule)
        """
        cls.STRATEGIES[name] = strategy_class
        logger.info(f"Registered strategy: {name}")
    
    @classmethod
    def create(
        cls,
        instance_id: str,
        config: 'Config',
        run_id: Optional[str] = None,
        **kwargs
    ) -> 'BaseAnalysisModule':
        """
        Create a strategy instance for the given instance_id.
        
        Loads strategy name and config from database, then instantiates
        the appropriate strategy class with instance-specific settings.
        
        Args:
            instance_id: Instance ID
            config: Trading bot config
            run_id: Run ID (for audit trail)
            **kwargs: Additional arguments to pass to strategy constructor
        
        Returns:
            Strategy instance
        
        Raises:
            ValueError: If instance not found or strategy not registered
        """
        from trading_bot.db.client import get_connection, release_connection, query_one
        
        # Load instance config from database
        conn = get_connection()
        try:
            instance = query_one(
                conn,
                "SELECT settings FROM instances WHERE id = ?",
                (instance_id,)
            )
            
            if not instance:
                raise ValueError(f"Instance not found: {instance_id}")
            
            settings = json.loads(instance.get('settings', '{}'))
            strategy_name = settings.get('strategy', 'prompt')  # Default to prompt
            strategy_config = settings.get('strategy_config', {})
            
        finally:
            release_connection(conn)
        
        # Get strategy class
        if strategy_name not in cls.STRATEGIES:
            raise ValueError(
                f"Unknown strategy: {strategy_name}. "
                f"Available: {list(cls.STRATEGIES.keys())}"
            )
        
        strategy_class = cls.STRATEGIES[strategy_name]
        
        # Create strategy instance with instance-specific config
        logger.info(
            f"Creating strategy '{strategy_name}' for instance {instance_id}",
            extra={"instance_id": instance_id, "strategy": strategy_name}
        )
        
        # Pass strategy_config to strategy constructor
        return strategy_class(
            config=config,
            instance_id=instance_id,
            run_id=run_id,
            strategy_config=strategy_config,
            **kwargs
        )
    
    @classmethod
    def get_available_strategies(cls) -> Dict[str, Type]:
        """Get all registered strategies."""
        return cls.STRATEGIES.copy()
    
    @classmethod
    def is_strategy_registered(cls, name: str) -> bool:
        """Check if a strategy is registered."""
        return name in cls.STRATEGIES

