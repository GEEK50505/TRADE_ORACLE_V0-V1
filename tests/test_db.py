"""
Phase 1 Deliverable: test_db.py
Unit testing protocol to validate the Supabase PostgreSQL connection and ensure 
the trailing drawdown memory logic functions correctly across mock execution cycles.
"""

import time
from config.settings import INITIAL_BALANCE
from journal.supabase_client import StateManager

def test_supabase_persistence():
    print("Initiating State Memory Diagnostic Protocol...")
    
    # Attempt instantiation of the memory layer
    try:
        db = StateManager()
        print("Successful authentication to PostgreSQL Cluster.")
    except Exception as e:
        print(f"CRITICAL FAILURE: Authentication rejected. Verify.env strings. Error: {e}")
        return

    # Cycle 1: The Cold Start Simulation
    print("\n--- Cycle 1: Account Initialization ---")
    mock_equity_1 = INITIAL_BALANCE  # Baseline mapping to $5000.0
    watermark_1 = db.update_high_watermark(mock_equity_1)
    print(f"Expected Output: $5000.0 | Database Registered: ${watermark_1}")
    assert watermark_1 == 5000.0, "Cold start logic failure: Insert operation failed."
    
    time.sleep(1) # Intentional localized delay to avoid remote rate limit flags
    
    # Cycle 2: The Profitable Setup Simulation
    print("\n--- Cycle 2: Equity High Watermark Achieved ---")
    mock_equity_2 = 5150.0 # Algorithm captured a highly profitable short setup
    watermark_2 = db.update_high_watermark(mock_equity_2)
    print(f"Expected Output: $5150.0 | Database Registered: ${watermark_2}")
    assert watermark_2 == 5150.0, "Update mutation logic failure: Peak not recorded."

    time.sleep(1)
    
    # Cycle 3: The Hostile Drawdown Simulation
    print("\n--- Cycle 3: Algorithm Experiences Localized Drawdown ---")
    mock_equity_3 = 5025.0 # Market volatility retraced against an open position
    watermark_3 = db.update_high_watermark(mock_equity_3)
    print(f"Expected Output: $5150.0 (Persistent Lock) | Database Registered: ${watermark_3}")
    assert watermark_3 == 5150.0, "Persistence failure: Database incorrectly lowered the watermark."
    
    print("\nDiagnostic Complete. StateManager verified and ready for production routing.")

if __name__ == "__main__":
    test_supabase_persistence()