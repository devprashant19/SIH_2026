"""The air-gap guard in conftest must make any outbound connection attempt fail."""

from __future__ import annotations

import socket

import pytest

from tests.conftest import NetworkAccessAttempted


def test_outbound_socket_is_blocked() -> None:
    with pytest.raises(NetworkAccessAttempted):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("203.0.113.1", 443))  # TEST-NET address; never actually reached


def test_loopback_is_not_blocked_by_the_guard() -> None:
    # Loopback is permitted (asyncio needs it); a refused connection proves the guard let it through.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        try:
            s.connect(("127.0.0.1", 9))
        except NetworkAccessAttempted:
            pytest.fail("loopback should not be blocked")
        except OSError:
            pass
