
from sysproduction.update_total_capital import update_total_capital

def update_total_capital_wrapper():
    

    import asyncio
    # Create or get an event loop for the current thread
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
            
    update_total_capital()