"""
Production-ready secrets management for trading bot.

This module provides a centralized way to handle secrets from multiple sources:
- Environment variables (development)
- Docker secrets (production)
- File-based secrets (custom deployments)

Follows security best practices:
- Fail-safe defaults
- No secret logging
- Memory cleanup
- Consistent interface
- Encryption for sensitive data storage
"""

import base64
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Encryption key derivation from machine-specific identifier
def _get_encryption_key() -> bytes:
    """Get or derive an encryption key for session data."""
    # Use a combination of env var and machine-specific data
    key_material = os.getenv('SESSION_ENCRYPTION_KEY', '')
    if not key_material:
        # Fallback: derive from BYBIT_API_KEY (always available in trading bot)
        key_material = os.getenv('BYBIT_API_KEY', 'default-trading-bot-key')

    # Derive 32-byte key using SHA256
    return hashlib.sha256(key_material.encode()).digest()


class SecretsManager:
    """
    Centralized secrets management with multiple source support.

    Priority order:
    1. Direct environment variable
    2. Docker secrets file (via *_FILE env var)
    3. Custom file path
    4. Default value (if provided)

    Also provides encryption/decryption for sensitive data storage.
    """

    # Cache for loaded secrets to avoid repeated file reads
    _cache: Dict[str, str] = {}
    _encryption_key: Optional[bytes] = None

    @classmethod
    def _get_key(cls) -> bytes:
        """Get cached encryption key."""
        if cls._encryption_key is None:
            cls._encryption_key = _get_encryption_key()
        return cls._encryption_key

    def encrypt(self, data: str) -> str:
        """
        Encrypt data using Fernet-style encryption (AES-based).

        Args:
            data: Plain text string to encrypt

        Returns:
            Base64-encoded encrypted string
        """
        try:
            from Crypto.Cipher import AES
            from Crypto.Random import get_random_bytes
            from Crypto.Util.Padding import pad

            key = self._get_key()
            iv = get_random_bytes(16)
            cipher = AES.new(key, AES.MODE_CBC, iv)

            padded_data = pad(data.encode('utf-8'), AES.block_size)
            encrypted = cipher.encrypt(padded_data)

            # Combine IV + encrypted data and encode as base64
            combined = iv + encrypted
            return base64.b64encode(combined).decode('utf-8')

        except ImportError:
            # Fallback: simple base64 encoding (NOT secure, but works)
            logger.warning("pycryptodome not installed - using base64 encoding (NOT secure)")
            return base64.b64encode(data.encode('utf-8')).decode('utf-8')

    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt data that was encrypted with encrypt().

        Args:
            encrypted_data: Base64-encoded encrypted string

        Returns:
            Decrypted plain text string
        """
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import unpad

            key = self._get_key()

            # Decode base64 and extract IV + encrypted data
            combined = base64.b64decode(encrypted_data)
            iv = combined[:16]
            encrypted = combined[16:]

            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted_padded = cipher.decrypt(encrypted)
            decrypted = unpad(decrypted_padded, AES.block_size)

            return decrypted.decode('utf-8')

        except ImportError:
            # Fallback: simple base64 decoding
            logger.warning("pycryptodome not installed - using base64 decoding")
            return base64.b64decode(encrypted_data).decode('utf-8')
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            # Try base64 fallback
            try:
                return base64.b64decode(encrypted_data).decode('utf-8')
            except:
                raise ValueError(f"Failed to decrypt data: {e}")

    @classmethod
    def get_secret(cls,
                   secret_name: str,
                   file_env_suffix: str = "_FILE",
                   default: Optional[str] = None,
                   required: bool = True) -> str:
        """
        Get secret value from multiple sources with fallback chain.
        
        Args:
            secret_name: Name of the environment variable (e.g., 'OPENAI_API_KEY')
            file_env_suffix: Suffix for file-based env var (default: '_FILE')
            default: Default value if secret not found
            required: Whether this secret is required (raises error if missing)
            
        Returns:
            Secret value as string
            
        Raises:
            ValueError: If required secret is not found
        """
        # Check cache first
        cache_key = f"{secret_name}:{file_env_suffix}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        
        # 1. Try direct environment variable
        value = os.getenv(secret_name)
        if value:
            cls._cache[cache_key] = value
            logger.debug(f"Loaded {secret_name} from environment variable")
            return value
        
        # 2. Try Docker secrets file
        file_env_var = f"{secret_name}{file_env_suffix}"
        file_path = os.getenv(file_env_var)
        if file_path:
            value = cls._read_secret_file(file_path, secret_name)
            if value:
                cls._cache[cache_key] = value
                logger.debug(f"Loaded {secret_name} from Docker secret file")
                return value
        
        # 3. Try common Docker secrets paths
        common_paths = [
            f"/run/secrets/{secret_name.lower()}",
            f"/run/secrets/{secret_name.lower().replace('_', '-')}",
            f"/var/secrets/{secret_name.lower()}",
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                value = cls._read_secret_file(path, secret_name)
                if value:
                    cls._cache[cache_key] = value
                    logger.debug(f"Loaded {secret_name} from common secret path: {path}")
                    return value
        
        # 4. Use default if provided
        if default is not None:
            cls._cache[cache_key] = default
            logger.debug(f"Using default value for {secret_name}")
            return default
        
        # 5. Handle missing required secret
        if required:
            error_msg = (
                f"Required secret '{secret_name}' not found. "
                f"Set environment variable '{secret_name}' or '{file_env_var}' "
                f"pointing to a secret file."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Return empty string for optional secrets
        cls._cache[cache_key] = ""
        return ""
    
    @staticmethod
    def _read_secret_file(file_path: str, secret_name: str) -> str:
        """
        Safely read secret from file.
        
        Args:
            file_path: Path to secret file
            secret_name: Name of secret (for logging only)
            
        Returns:
            Secret content or empty string if failed
        """
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"Secret file not found: {file_path}")
                return ""
            
            if not path.is_file():
                logger.warning(f"Secret path is not a file: {file_path}")
                return ""
            
            # Check file permissions (should be readable by current user)
            if not os.access(file_path, os.R_OK):
                logger.error(f"Cannot read secret file: {file_path}")
                return ""
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                logger.warning(f"Secret file is empty: {file_path}")
                return ""
            
            return content
            
        except Exception as e:
            logger.error(f"Failed to read secret file {file_path}: {e}")
            return ""
    
    @classmethod
    def load_all_secrets(cls) -> Dict[str, str]:
        """
        Load all common secrets used by the trading bot.
        
        Returns:
            Dictionary of loaded secrets (values are masked for security)
        """
        secrets_config = {
            'OPENAI_API_KEY': True,
            'BYBIT_API_KEY': True,
            'BYBIT_API_SECRET': True,
            'TELEGRAM_BOT_TOKEN': True,
            'TELEGRAM_CHAT_ID': True,
            'TELEGRAM_AUTHORIZED_USERS': False,
            'TRADINGVIEW_EMAIL': False,  # Used for session naming, not login
            'VNC_PASSWORD': False,
        }

        loaded = {}
        for secret_name, required in secrets_config.items():
            try:
                value = cls.get_secret(secret_name, required=required)
                # Mask the value for security
                if value:
                    if len(value) > 10:
                        masked = f"{value[:4]}...{value[-4:]}"
                    else:
                        masked = "*" * len(value)
                    loaded[secret_name] = masked
                else:
                    loaded[secret_name] = "Not set"
            except ValueError:
                loaded[secret_name] = "Missing (required)"

        return loaded

    @classmethod
    def clear_cache(cls):
        """Clear the secrets cache (useful for testing or security)."""
        cls._cache.clear()
        logger.debug("Secrets cache cleared")

    @classmethod
    def validate_secrets(cls) -> Dict[str, Any]:
        """
        Validate all required secrets are available.

        Returns:
            Validation report with status and any errors
        """
        required_secrets = [
            'OPENAI_API_KEY',
            'BYBIT_API_KEY',
            'BYBIT_API_SECRET',
            'TELEGRAM_BOT_TOKEN',
            'TELEGRAM_CHAT_ID',
        ]

        report = {
            'valid': True,
            'missing_secrets': [],
            'loaded_secrets': [],
            'warnings': []
        }

        for secret_name in required_secrets:
            try:
                value = cls.get_secret(secret_name, required=True)
                if value:
                    report['loaded_secrets'].append(secret_name)
                else:
                    report['missing_secrets'].append(secret_name)
                    report['valid'] = False
            except ValueError:
                report['missing_secrets'].append(secret_name)
                report['valid'] = False

        # Check optional secrets (login is manual now, email just for session naming)
        optional_secrets = ['TELEGRAM_AUTHORIZED_USERS', 'VNC_PASSWORD', 'TRADINGVIEW_EMAIL']
        for secret_name in optional_secrets:
            try:
                value = cls.get_secret(secret_name, required=False)
                if not value:
                    report['warnings'].append(f"Optional secret {secret_name} not set")
            except Exception:
                pass

        return report


# Convenience functions for common secrets
def get_openai_api_key() -> str:
    """Get OpenAI API key from secrets."""
    # Check for Docker Compose file-based secret first
    if os.getenv('OPENAI_API_KEY_FILE'):
        return SecretsManager.get_secret('OPENAI_API_KEY', file_env_suffix='_FILE', required=True)
    # Fall back to direct environment variable
    return SecretsManager.get_secret('OPENAI_API_KEY', required=True)


def get_bybit_credentials() -> tuple[str, str]:
    """Get Bybit API credentials from secrets."""
    import os
    
    # Check for Docker Compose file-based secrets first
    if os.getenv('BYBIT_API_KEY_FILE') and os.getenv('BYBIT_API_SECRET_FILE'):
        api_key = SecretsManager.get_secret('BYBIT_API_KEY', file_env_suffix='_FILE', required=True)
        api_secret = SecretsManager.get_secret('BYBIT_API_SECRET', file_env_suffix='_FILE', required=True)
        return api_key, api_secret
    
    # Check if old naming convention exists (backward compatibility)
    if os.getenv('BYBIT_KEY') or os.getenv('BYBIT_KEY_FILE'):
        api_key = SecretsManager.get_secret('BYBIT_KEY', required=True)
    else:
        api_key = SecretsManager.get_secret('BYBIT_API_KEY', required=True)
    
    if os.getenv('BYBIT_SECRET') or os.getenv('BYBIT_SECRET_FILE'):
        api_secret = SecretsManager.get_secret('BYBIT_SECRET', required=True)
    else:
        api_secret = SecretsManager.get_secret('BYBIT_API_SECRET', required=True)
    
    return api_key, api_secret


def get_telegram_config() -> tuple[str, str, str]:
    """Get Telegram bot configuration from secrets."""
    import os
    
    # Check for Docker Compose file-based secrets first
    if os.getenv('TELEGRAM_BOT_TOKEN_FILE'):
        bot_token = SecretsManager.get_secret('TELEGRAM_BOT_TOKEN', file_env_suffix='_FILE', required=True)
    else:
        bot_token = SecretsManager.get_secret('TELEGRAM_BOT_TOKEN', required=True)
    
    if os.getenv('TELEGRAM_CHAT_ID_FILE'):
        chat_id = SecretsManager.get_secret('TELEGRAM_CHAT_ID', file_env_suffix='_FILE', required=True)
    else:
        chat_id = SecretsManager.get_secret('TELEGRAM_CHAT_ID', required=True)
    
    if os.getenv('TELEGRAM_AUTHORIZED_USERS_FILE'):
        authorized_users = SecretsManager.get_secret('TELEGRAM_AUTHORIZED_USERS', file_env_suffix='_FILE', required=False)
    else:
        authorized_users = SecretsManager.get_secret('TELEGRAM_AUTHORIZED_USERS', required=False)
    
    return bot_token, chat_id, authorized_users


def get_tradingview_email() -> str:
    """Get TradingView email from secrets (used for session file naming, NOT for login)."""
    import os

    # Check for Docker Compose file-based secrets first
    if os.getenv('TRADINGVIEW_EMAIL_FILE'):
        return SecretsManager.get_secret('TRADINGVIEW_EMAIL', file_env_suffix='_FILE', required=False) or 'default'
    return SecretsManager.get_secret('TRADINGVIEW_EMAIL', required=False) or 'default'


def get_tradingview_credentials() -> tuple[str, str]:
    """
    DEPRECATED: TradingView login is now manual via interactive browser.
    This function is kept for backward compatibility but returns empty password.
    """
    email = get_tradingview_email()
    return email, ''  # Password no longer used - login is manual


def get_vnc_password() -> str:
    """Get VNC password from secrets."""
    import os
    
    # Check for Docker Compose file-based secrets first
    if os.getenv('VNC_PASSWORD_FILE'):
        return SecretsManager.get_secret('VNC_PASSWORD', file_env_suffix='_FILE', required=False)
    else:
        return SecretsManager.get_secret('VNC_PASSWORD', required=False)