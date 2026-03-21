"""
Pytest configuration and fixtures for Story Forge tests.
"""

import pytest
from unittest.mock import patch
from cryptography.fernet import Fernet


@pytest.fixture(autouse=True)
def mock_keyring():
    """Mock keyring to avoid desktop environment dependency in CI."""
    fake_key = Fernet.generate_key().decode()
    
    with patch("keyring.get_password", return_value=fake_key):
        with patch("keyring.set_password", return_value=None):
            yield
