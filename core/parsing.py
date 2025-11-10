# core/parsing.py
"""Utility functions for parsing user input amounts."""


def parse_amount(amount_str: str, max_possible: int = None) -> int | str | None:
    """
    Parse amount string with support for:
    - Plain numbers: "5", "100"
    - Suffixes: "5k", "2m", "1b"
    - Special: "all", "half", "max"
    
    Returns:
    - int: parsed numeric amount
    - str: "all" for special all handling
    - None: invalid input
    
    Args:
        amount_str: The user input string
        max_possible: Optional maximum value for "half" calculation
    """
    if not amount_str:
        return None
    
    amount_str = str(amount_str).lower().strip()
    
    # Handle special keywords
    if amount_str in ["all", "max"]:
        return "all"
    
    if amount_str == "half":
        if max_possible is not None:
            return max(1, max_possible // 2)
        return "all"  # fallback to all if we can't calculate half
    
    # Handle numeric with suffixes
    if amount_str[-1] in ['k', 'm', 'b']:
        suffix = amount_str[-1]
        try:
            base = float(amount_str[:-1])
            multipliers = {'k': 1_000, 'm': 1_000_000, 'b': 1_000_000_000}
            return int(base * multipliers[suffix])
        except (ValueError, IndexError):
            return None
    
    # Handle plain numbers
    try:
        return int(float(amount_str))
    except ValueError:
        return None
