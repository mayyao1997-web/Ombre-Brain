"""Small, testable intent rules for the Discord interface."""

import re


_CALL_MAY = re.compile(
    r"(?:帮我|麻烦|请)?\s*(?:叫|通知|呼唤|喊)(?:一下)?\s*@?May(?![’'sS])",
    re.IGNORECASE,
)


def should_notify_may(text: str) -> bool:
    """Return true only for an explicit request to summon or notify May."""
    return _CALL_MAY.search(text) is not None
