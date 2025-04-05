# mongo_program.py
from program_base import BaseProgram
import subprocess
import os
from sysdata.data_blob import dataBlob  # Assumes dataBlob provides a mongo_db() method
from pymongo import MongoClient, errors

class MongoProgram(BaseProgram):
    def __init__(self, config):
        super().__init__(config)
        # Use the inherited status_file or one from config.
        # Set the monitor function to our custom monitor.
        self.monitor_func = self.custom_monitor

    @BaseProgram.record_start
    def start(self):
        """
        Starts the Mongo process using the command:
        bash -c "source $HOME/.profile; mongod --dbpath $MONGO_DATA"
        Returns the spawned process's PID.
        """
        self.status_logger.debug(f"Starting Mongo Program: {self.name}")
        try:
            self.process = subprocess.Popen(
                ["bash", "-c", "source $HOME/.profile && nohup mongod --dbpath \"$MONGO_DATA\" >> \"$HOME/mongod.log\" 2>&1 &"],
                preexec_fn=os.setsid
            )
            self.status_logger.info(f"Started Mongo Program '{self.name}' with PID {self.process.pid}")
            return self.process.pid
        except Exception as e:
            self.status_logger.error(f"Failed to start Mongo Program '{self.name}': {e}")
            return None

    @BaseProgram.record_stop
    def stop(self):
        """
        Stops the Mongo process.
        """
        self.status_logger.debug(f"Stopping Mongo Program: {self.name}")
        if self.process:
            try:
                self.process.terminate()
                self.status_logger.info(f"Mongo Program '{self.name}' terminated.")
            except Exception as e:
                self.status_logger.error(f"Error stopping Mongo Program '{self.name}': {e}")

    def custom_monitor(self):
        """
        Custom monitoring function for the Mongo process.
        It calls dataBlob().mongo_db() to check if a connection to the Mongo server can be made.
        If an exception is raised, the monitor attempts to restart the process.
        """
        try:
            d = dataBlob()
            # mongo_db() should throw an exception if the connection fails.
            client = d.mongo_db.client
            client.admin.command('ping')
            self.status_logger.info("Mongo monitor check succeeded.")
            return False
        except errors.ServerSelectionTimeoutError as e:
            self.status_logger.error(f"Mongo monitor check failed: {e}")
            return True
