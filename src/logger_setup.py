import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logger(name, log_file, level=logging.DEBUG):
    """Setup a logger with a rotating file handler (max 10 MB per file). 
       If the log file exists and has content, a restart header is appended.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Only add handlers if they haven't been set up already.
    if not logger.handlers:
        # Ensure the directory for the log file exists.
        dir_path = os.path.dirname(log_file)
        if dir_path and not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
            except Exception as e:
                print(f"Error creating directory {dir_path}: {e}")
        
        # Check if log file exists and has content; if so, append the restart header.
        if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
            try:
                with open(log_file, 'a') as f:
                    f.write("\n====================== [Process Manager Restarted] =======================\n")
            except Exception as e:
                print(f"Error writing restart header to {log_file}: {e}")

        handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger
