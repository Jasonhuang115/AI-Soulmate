from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def translate(
    expression: str | None,
    motion: str | None,
    avatar_map: dict[str, Any],
) -> dict[str, Any]:
    expressions = avatar_map.get("expressions", {})
    motions = avatar_map.get("motions", {})
    fallback = avatar_map.get("fallback_expression", "neutral")
    expression_id = None
    if expression:
        expression_id = expressions.get(expression)
        if expression_id is None:
            logger.warning("missing expression mapping: %s", expression)
            expression_id = expressions.get(fallback)
    motion_ref = motions.get(motion) if motion else None
    if motion and motion_ref is None:
        logger.warning("missing motion mapping: %s", motion)
    return {
        "expression_id": expression_id,
        "group": (motion_ref or {}).get("group"),
        "index": (motion_ref or {}).get("index"),
    }
