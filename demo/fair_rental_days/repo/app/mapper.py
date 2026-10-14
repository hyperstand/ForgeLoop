"""Buggy baseline: drops fair_rental_days (always 0). Demo agent must fix this."""


def map_rental(doc):
    return {
        "fair_rental_days": 0,
        "other_expenses": doc.get("other_expenses", 0),
    }
