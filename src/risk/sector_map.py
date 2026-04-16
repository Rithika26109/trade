"""
Sector Map
──────────
Static mapping of NIFTY 50 stocks to their GICS sectors.
Used for sector-aware position limits (avoid concentration in one sector).
"""

SECTOR_MAP = {
    # Banking / Financial Services
    "HDFCBANK": "Banking",
    "ICICIBANK": "Banking",
    "KOTAKBANK": "Banking",
    "SBIN": "Banking",
    "AXISBANK": "Banking",
    "INDUSINDBK": "Banking",
    "BAJFINANCE": "Financial Services",
    "BAJAJFINSV": "Financial Services",
    "HDFCLIFE": "Financial Services",
    "SBILIFE": "Financial Services",

    # IT / Technology
    "TCS": "IT",
    "INFY": "IT",
    "WIPRO": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "LTIMindtree": "IT",

    # Energy / Oil & Gas
    "RELIANCE": "Energy",
    "ONGC": "Energy",
    "NTPC": "Energy",
    "POWERGRID": "Energy",
    "ADANIENT": "Energy",
    "ADANIPORTS": "Energy",
    "COALINDIA": "Energy",

    # FMCG / Consumer
    "ITC": "FMCG",
    "HINDUNILVR": "FMCG",
    "NESTLEIND": "FMCG",
    "TATACONSUM": "FMCG",
    "BRITANNIA": "FMCG",

    # Telecom
    "BHARTIARTL": "Telecom",

    # Infrastructure / Engineering
    "LT": "Infrastructure",
    "ULTRACEMCO": "Infrastructure",
    "GRASIM": "Infrastructure",
    "SHREECEM": "Infrastructure",

    # Automobile
    "MARUTI": "Automobile",
    "TATAMOTORS": "Automobile",
    "M&M": "Automobile",
    "BAJAJ-AUTO": "Automobile",
    "HEROMOTOCO": "Automobile",
    "EICHERMOT": "Automobile",

    # Pharma / Healthcare
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "APOLLOHOSP": "Pharma",

    # Metals / Mining
    "TATASTEEL": "Metals",
    "HINDALCO": "Metals",
    "JSWSTEEL": "Metals",

    # Others
    "TITAN": "Consumer Discretionary",
    "ASIANPAINT": "Consumer Discretionary",
    "WIPRO": "IT",
}


def get_sector(symbol: str) -> str:
    """Get sector for a symbol. Returns 'Unknown' if not found."""
    return SECTOR_MAP.get(symbol, "Unknown")


def are_same_sector(symbol1: str, symbol2: str) -> bool:
    """Check if two symbols are in the same sector."""
    s1 = get_sector(symbol1)
    s2 = get_sector(symbol2)
    if s1 == "Unknown" or s2 == "Unknown":
        return False
    return s1 == s2
