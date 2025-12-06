"""
Login State Manager - Manages manual login state for dashboard communication.

This module provides a simple file-based state management for coordinating
manual login flow between the Python bot and the Next.js dashboard.

States:
- idle: No login required, bot is operating normally
- waiting_for_login: Bot detected login is required, waiting for user to login
- login_confirmed: User confirmed login in dashboard, bot should verify and continue
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# State file location - in the data directory for easy access
STATE_FILE = Path(__file__).parent.parent / "data" / "login_state.json"


class LoginState:
    """Enum-like class for login states."""
    IDLE = "idle"
    WAITING_FOR_LOGIN = "waiting_for_login"
    LOGIN_CONFIRMED = "login_confirmed"
    BROWSER_OPENED = "browser_opened"


def _ensure_state_file() -> None:
    """Ensure the state file directory exists."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_login_state() -> dict:
    """Get the current login state.
    
    Returns:
        dict with keys: state, message, timestamp, browser_opened
    """
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Error reading login state: {e}")
    
    # Default state
    return {
        "state": LoginState.IDLE,
        "message": None,
        "timestamp": None,
        "browser_opened": False
    }


def set_login_state(state: str, message: Optional[str] = None, browser_opened: bool = False) -> None:
    """Set the login state.
    
    Args:
        state: One of LoginState values
        message: Optional message to display to user
        browser_opened: Whether the browser has been opened for login
    """
    try:
        _ensure_state_file()
        data = {
            "state": state,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "browser_opened": browser_opened
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Login state set to: {state}")
    except Exception as e:
        logger.error(f"Error writing login state: {e}")


def set_waiting_for_login(message: str = "Manual login required for TradingView") -> None:
    """Set state to waiting for login."""
    set_login_state(LoginState.WAITING_FOR_LOGIN, message, browser_opened=False)


def set_browser_opened() -> None:
    """Mark that browser has been opened for login."""
    current = get_login_state()
    set_login_state(
        LoginState.WAITING_FOR_LOGIN, 
        current.get("message", "Browser opened - please login"),
        browser_opened=True
    )


def set_login_confirmed() -> None:
    """User confirmed login from dashboard - bot should verify and continue."""
    set_login_state(LoginState.LOGIN_CONFIRMED, "Login confirmed by user")


def set_idle() -> None:
    """Reset to idle state."""
    set_login_state(LoginState.IDLE)


def is_waiting_for_login() -> bool:
    """Check if bot is waiting for manual login."""
    state = get_login_state()
    return state.get("state") == LoginState.WAITING_FOR_LOGIN


def is_login_confirmed() -> bool:
    """Check if user has confirmed login."""
    state = get_login_state()
    return state.get("state") == LoginState.LOGIN_CONFIRMED


def clear_state() -> None:
    """Clear the state file."""
    try:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
    except Exception as e:
        logger.debug(f"Error clearing login state: {e}")

