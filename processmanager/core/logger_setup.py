import os
import sys
import logging
from logging import FileHandler
from ..config import Config

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

"""
if name == main:

    setup_base_logging(level, log_file, mark restart) -> sets root config only
        - use logging.baseConfig
        - set root level, console stream, truncating fh
        - put mark restart here since setting up base logging indicates a restart by design
        
elsewhere in code:
    get_logger(name, level)
    
    
    
"""            

def setup_base_logging(log_file, level=logging.DEBUG, mark_restart=False):
    """
    Sets up the root logger to write to a shared file and stdout.
    All named loggers will inherit from this.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.hasHandlers():
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(name)s] - %(message)s')

        # Create log file directory if needed
        dir_path = os.path.dirname(log_file)
        if dir_path and not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)

        # Optional restart header
        if mark_restart and os.path.exists(log_file) and os.path.getsize(log_file) > 0:
            with open(log_file, 'a') as f:
                f.write("\n====================== [Process Manager Restarted] =======================\n")

        # File handler (shared)
        file_handler = TruncatingFileHandler(log_file, maxBytes=4 * 1024)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)

        # Stream handler (console)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(level)
        root_logger.addHandler(stream_handler)

def get_logger(name, level=logging.DEBUG):
    """
    Returns a named logger that uses the base handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = True  # Ensure it bubbles up to root handlers
    return logger