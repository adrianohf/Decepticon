"""Decepticon logging — thin wrapper around stdlib logging."""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Get a namespaced logger for the given module.

    Usage:
        from decepticon.core.logging import get_logger
        log = get_logger("auth.manager")
        log.info("something happened")
    """
    return logging.getLogger(f"decepticon.{name}")
