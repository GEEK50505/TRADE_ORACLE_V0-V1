"""
Phase 1 Deliverable: journal/supabase_client.py
This module acts as the persistent memory system for the TRADE_ORACLE architecture. 
It establishes a secure connection to the Supabase PostgreSQL cluster, allowing the 
algorithm to track its absolute peak equity and mathematically defend against 
institutional trailing drawdown limits across all execution lifecycles.
"""

import os
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
            self.supabase.table('account_state').insert({'id': 1, 'high_watermark': current_equity}).execute()
            return current_equity
            
        # Extract the securely stored historical peak from the JSON response object
        saved_watermark = response.data['high_watermark']
        
        # Logical Evaluation: Does the current equity exceed the historic peak?
        if current_equity > saved_watermark:
            print(f"Algorithm Peak Update: New high watermark locked at ${current_equity}")
            # Mutate the cloud state to reflect the new algorithmic ceiling via update operation
            self.supabase.table('account_state').update({'high_watermark': current_equity}).eq('id', 1).execute()
            return current_equity
            
        # If the account is in a localized drawdown, return the persistent historical peak
        # This value is passed directly to the mathematical risk manager module.
        return saved_watermark