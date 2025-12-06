"""Centralized path management for the trading bot prototype.

This module provides a single source of truth for all file paths used throughout
the application, eliminating hardcoded paths and ensuring consistency.
"""

import os
from pathlib import Path
from typing import Optional

class PathManager:
    """Centralized path manager for the trading bot prototype."""

    def __init__(self, base_dir: Optional[str] = None):
        """
        Initialize the path manager.

        Args:
            base_dir: Optional base directory. If None, uses the prototype directory.
        """
        # Determine base directory - default to V2/prototype directory
        if base_dir is None:
            # Find the prototype directory by looking for known markers
            current_file = Path(__file__)
            if "V2" in str(current_file) and "prototype" in str(current_file):
                # We're already in the prototype structure
                self.base_dir = current_file.parent.parent.parent.parent
            else:
                # Fallback: assume we're in a standard Python project structure
                self.base_dir = current_file.parent.parent.parent
        else:
            self.base_dir = Path(base_dir).resolve()

        # Ensure we have the expected structure
        if not (self.base_dir / "python").exists():
            # Try to find the correct base by looking for the python directory
            found_base = None
            for parent in [self.base_dir] + list(self.base_dir.parents):
                if (parent / "python").exists():
                    found_base = parent
                    break

            if found_base:
                self.base_dir = found_base
            else:
                raise RuntimeError(f"Could not find prototype base directory from {self.base_dir}")

    @property
    def prototype_root(self) -> Path:
        """Get the root of the V2 prototype directory."""
        return self.base_dir

    @property
    def python_root(self) -> Path:
        """Get the root of the Python source directory."""
        return self.prototype_root / "python"

    @property
    def trading_bot_root(self) -> Path:
        """Get the root of the trading_bot package."""
        return self.python_root / "trading_bot"

    @property
    def config_yaml_path(self) -> Path:
        """Path to the main config.yaml file."""
        return self.prototype_root / "config.yaml"

    @property
    def data_dir(self) -> Path:
        """Path to the data directory."""
        return self.prototype_root / "data"

    @property
    def charts_dir(self) -> Path:
        """Path to the charts directory."""
        return self.data_dir / "charts"

    @property
    def logs_dir(self) -> Path:
        """Path to the logs directory."""
        return self.prototype_root / "logs"

    @property
    def db_dir(self) -> Path:
        """Path to the database directory (same as data_dir)."""
        return self.data_dir

    @property
    def trading_db_path(self) -> Path:
        """Path to the main trading database."""
        return self.db_dir / "trading.db"

    @property
    def backtests_db_path(self) -> Path:
        """Path to the backtests database."""
        return self.db_dir / "backtests.db"

    @property
    def candle_store_db_path(self) -> Path:
        """Path to the candle store database."""
        return self.db_dir / "candle_store.db"

    @property
    def config_dir(self) -> Path:
        """Path to the config directory within trading_bot."""
        return self.trading_bot_root / "config"

    @property
    def model_costs_path(self) -> Path:
        """Path to the model costs JSON file."""
        return self.config_dir / "model_costs.json"

    @property
    def session_files_dir(self) -> Path:
        """Path to the session files directory."""
        return self.data_dir

    @property
    def env_local_path(self) -> Path:
        """Path to the .env.local file."""
        return self.prototype_root / ".env.local"

    def get_relative_path(self, relative_path: str) -> Path:
        """
        Get a path relative to the prototype root.

        Args:
            relative_path: Path relative to prototype root

        Returns:
            Absolute path
        """
        return self.prototype_root / relative_path

    def ensure_directories_exist(self):
        """Ensure all required directories exist."""
        required_dirs = [
            self.data_dir,
            self.charts_dir,
            self.logs_dir,
            self.db_dir,
            self.config_dir
        ]

        for dir_path in required_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)

# Global singleton instance for convenience
_path_manager = None

def get_path_manager() -> PathManager:
    """Get the global path manager instance."""
    global _path_manager
    if _path_manager is None:
        _path_manager = PathManager()
    return _path_manager

def reset_path_manager():
    """Reset the global path manager (useful for testing)."""
    global _path_manager
    _path_manager = None

# Convenience functions for common paths
def get_config_yaml_path() -> Path:
    """Get the path to config.yaml."""
    return get_path_manager().config_yaml_path

def get_trading_db_path() -> Path:
    """Get the path to the trading database."""
    return get_path_manager().trading_db_path

def get_charts_dir() -> Path:
    """Get the path to the charts directory."""
    return get_path_manager().charts_dir

def get_logs_dir() -> Path:
    """Get the path to the logs directory."""
    return get_path_manager().logs_dir

def get_model_costs_path() -> Path:
    """Get the path to the model costs JSON file."""
    return get_path_manager().model_costs_path