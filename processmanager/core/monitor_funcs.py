# monitor_funcs.py

def default_monitor(program):
    """
    Default monitoring function.
    Checks if the program's process is not running.
    
    Returns:
        bool: True if the program is not running (i.e., needs to be restarted), otherwise False.
    """
    if program.process is None:
        return True
    return program.process.poll() is not None

def monitor_tws(program):
    """
    Custom monitoring function for the 'tws' program.
    
    This function first calls the default_monitor function to check the basic process status.
    If the default monitor indicates that the process has terminated, this function returns True.
    
    You can add additional custom logic below (e.g., checking for specific error logs, resource usage,
    or other custom conditions) and return True if any of those conditions require a restart.
    
    Returns:
        bool: True if the program needs to be restarted, False otherwise.
    """
    # Check the basic process status using the default monitor.
    if default_monitor(program):
        return True

    # Insert additional custom checks here if needed.
    # For example:
    # if custom_error_detected(program):
    #     return True

    # If no conditions require a restart, return False.
    return False