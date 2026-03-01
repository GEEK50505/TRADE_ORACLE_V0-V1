"""
Phase 1 Deliverable: journal/supabase_client.py
This module acts as the persistent memory system for the TRADE_ORACLE architecture. 
It establishes a secure connection to the Supabase PostgreSQL cluster, allowing the 
algorithm to track its absolute peak equity and mathematically defend against 
institutional trailing drawdown limits across all execution lifecycles.
"""

import os

# monkey‑patch gotrue.SyncClient to ignore 'proxy' keyword
try:
    from gotrue.http_clients import SyncClient as _GotrueSyncClient
    _orig_init = _GotrueSyncClient.__init__
    def _patched_init(self, *args, proxy=None, **kwargs):
        # drop proxy argument, forward rest
        return _orig_init(self, *args, **kwargs)
    _GotrueSyncClient.__init__ = _patched_init
except ImportError:
    # if gotrue version changes or not installed, ignore
    pass

from supabase import create_client, Client

class StateManager:
    
    def __init__(self):
        """
        Initializes the Supabase Python Client by ingesting the environment variables 
        established in the isolated workspace, establishing a persistent, secure 
        connection to the remote PostgreSQL cluster.
        """
        url: str = os.getenv("SUPABASE_URL")
        key: str = os.getenv("SUPABASE_KEY")
        
        # Instantiate the official Supabase Client object
        self.supabase: Client = create_client(url, key)

    def update_high_watermark(self, current_equity: float) -> float:
        """
        Retrieves the historical peak equity and autonomously updates it if the 
        current live equity measurement establishes a new global high watermark.
        
        Args:
            current_equity (float): The combined value of the baseline account balance 
                                    and any active floating PnL.
                                    
        Returns:
            float: The absolute highest recorded equity watermark.
        """
        
        # Query the 'account_state' table for the singleton record with id = 1
        # Execution of the basic select operation documented by supabase-py
        response = self.supabase.table('account_state').select('high_watermark').eq('id', 1).execute()
        
        # Determine if the record exists; if empty, initialize the database state
        if not response.data:
            print("System Memory Initialize: Establishing baseline high watermark.")
            # Execute an insert operation to establish the foundational metric
            insert_resp = self.supabase.table('account_state').insert({'id': 1, 'high_watermark': current_equity}).execute()
            # verbose logging for debugging: show response metadata
            try:
                print('INSERT response data:', insert_resp.data)
                print('INSERT response count:', getattr(insert_resp, 'count', None))
            except Exception:
                print('INSERT response (no metadata available)')
            return current_equity
            
        # Supabase returns a list of rows; use the first entry
        row = response.data[0] if isinstance(response.data, list) else response.data
        saved_watermark = row.get('high_watermark')
        
        # Logical Evaluation: Does the current equity exceed the historic peak?
        if current_equity > saved_watermark:
            print(f"Algorithm Peak Update: Attempting to lock new high watermark at ${current_equity}")
            # Mutate the cloud state to reflect the new algorithmic ceiling via update operation
            update_resp = self.supabase.table('account_state').update({'high_watermark': current_equity}).eq('id', 1).execute()
            # verbose logging for debugging: show response metadata
            try:
                print('UPDATE response data:', update_resp.data)
                print('UPDATE response count:', getattr(update_resp, 'count', None))
            except Exception:
                print('UPDATE response (no metadata available)')
            # the APIResponse may still return the original value if the update was blocked
            if update_resp.data and isinstance(update_resp.data, list):
                updated_row = update_resp.data[0]
            elif update_resp.data and isinstance(update_resp.data, dict):
                updated_row = update_resp.data
            else:
                updated_row = None
            if updated_row:
                new_value = updated_row.get('high_watermark', saved_watermark)
                if new_value != saved_watermark:
                    print(f"Algorithm Peak Update: New high watermark confirmed in database: ${new_value}")
                else:
                    print("WARNING: attempted watermark update did not persist (check RLS/policies)")
                saved_watermark = new_value
            else:
                print("WARNING: no data returned from update operation; retaining previous watermark")
            return saved_watermark
            
        # If the account is in a localized drawdown, return the persistent historical peak
        # This value is passed directly to the mathematical risk manager module.
        return saved_watermark