"""Credit cost map per AI endpoint.

Each endpoint that consumes AI resources has an associated credit cost.
The cost is debited from the user's credit balance before the AI call.
"""

from __future__ import annotations

# Cost in credits per AI endpoint call
ENDPOINT_CREDIT_COST: dict[str, int] = {
    "/smart-text": 1,
    "/describe-gif": 1,
    "/enhance-document": 3,
    "/generate-documentation": 3,
    "/format-and-export": 2,
    "/videos/raw": 5,  # video upload (raw stream)
    "/videos/youtube": 5,  # YouTube import
    "default": 1,
}


def get_credit_cost(endpoint: str) -> int:
    """Return the credit cost for a given endpoint path.

    Matches by checking if any known pattern is contained in the endpoint string.
    Falls back to the ``"default"`` cost if no pattern matches.

    Args:
        endpoint: The request path (e.g. ``"/smart-text"``, ``"/videos/raw"``).

    Returns:
        Number of credits required.
    """
    for pattern, cost in ENDPOINT_CREDIT_COST.items():
        if pattern == "default":
            continue
        if pattern in endpoint:
            return cost
    return ENDPOINT_CREDIT_COST["default"]
