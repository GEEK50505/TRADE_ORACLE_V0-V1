# utils/helpers.py
def format_number(num, decimals=2):
    """Clean number formatting"""
    return f"{num:,.{decimals}f}"

def print_header(title):
    """Print nice headers"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)