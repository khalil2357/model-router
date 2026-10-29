"""multi-model-router — Python plugin entry point.
Registers middleware or route handlers if needed.
"""
from __future__ import annotations
import logging

logger = logging.getLogger("multi-model-router")

def register(ctx) -> None:
    logger.info("multi-model-router plugin registered")
