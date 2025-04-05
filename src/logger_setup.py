import os
import logging
from logging import FileHandler

class TruncatingFileHandler(FileHandler):
    """
    A custom logging handler that writes log records to a single file.
    When the file exceeds maxBytes (10 MB by default), it truncates the beginning of the file,
    preserving only the most recent data up to maxBytes.
    """
    def __init__(self, filename, mode='a', maxBytes=10 * 1024 * 1024, encoding=None, delay=False):
        self.maxBytes = maxBytes
        super().__init__(filename, mode, encoding, delay)
    
    def emit(self, record):
        try:
            super().emit(record)
            self.flush()
            self._truncate_if_needed()
        except Exception:
            self.handleError(record)
    
    def _truncate_if_needed(self):
        try:
            # Check if file exceeds maxBytes
            if os.path.getsize(self.baseFilename) > self.maxBytes:
                with open(self.baseFilename, 'rb') as f:
                    # Seek to the position where the last maxBytes starts.
                    f.seek(-self.maxBytes, os.SEEK_END)
                    data = f.read()
                # Write the last maxBytes back to the file.
                with open(self.baseFilename, 'wb') as f:
                    f.write(data)
                # Reopen the stream to update the file handle.
                if self.stream:
                    self.stream.close()
                self.stream = self._open()
        except Exception as e:
            self.handleError(e)

def setup_logger(name, log_file, level=logging.DEBUG):
    """
    Sets up a logger using the TruncatingFileHandler.
    If the log file already exists and contains data, a restart header is appended.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Add the handler only if none have been added yet.
    if not logger.handlers:
        # Ensure the directory for the log file exists.
        dir_path = os.path.dirname(log_file)
        if dir_path and not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
            except Exception as e:
                print(f"Error creating directory {dir_path}: {e}")
        
        # Append a restart header if the log file exists and is not empty.
        if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
            try:
                with open(log_file, 'a') as f:
                    f.write("\n====================== [Process Manager Restarted] =======================\n")
            except Exception as e:
                print(f"Error writing restart header to {log_file}: {e}")

        handler = TruncatingFileHandler(log_file, maxBytes=10 * 1024 * 1024)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger

def setup_process_manager_logger(log_file="logs/process_manager.log", level=logging.DEBUG):
    """
    Convenience function for setting up a global process manager logger.
    """
    return setup_logger("ProcessManager", log_file, level)
