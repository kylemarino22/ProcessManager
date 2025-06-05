
from sysproduction.update_total_capital import update_total_capital
from sysproduction.update_sampled_contracts import update_sampled_contracts

def setup_asyncio():
    
    import asyncio
    # Create or get an event loop for the current thread
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

def update_total_capital_wrapper():
    
    setup_asyncio()
    update_total_capital()

def update_sampled_contracts_wrapper():
    
    setup_asyncio()
    update_sampled_contracts()