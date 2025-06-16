#!/usr/bin/env python
import subprocess
import logging

from sysproduction.backup_db_to_csv import backup_db_to_csv
from sysproduction.backup_mongo_data_as_dump import backup_mongo_data_as_dump
from sysproduction.backup_state_files import backup_state_files
from sysproduction.backup_parquet_data_to_remote import backup_parquet_data_to_remote
from sysproduction.clean_truncate_backtest_states import clean_truncate_backtest_states
from sysproduction.clean_truncate_echo_files import clean_truncate_echo_files
from sysproduction.clean_truncate_log_files import clean_truncate_log_files

# Configure the root logger. Adjust level and format as needed.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("backup")

def backup():
    # --- Backup Procedures ---
    # Backup Minecraft server with streamed output to logger.
    mc_script = "/home/kyle/mc-server-backups/backup-script.sh"
    logger.info("Starting Minecraft server backup...")
    try:
        process = subprocess.Popen(
            ["bash", mc_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        # Stream each line as it appears
        for line in process.stdout:
            logger.debug("Minecraft backup: %s", line.rstrip())
        process.stdout.close()
        returncode = process.wait()
        if returncode == 0:
            logger.info("Minecraft backup completed successfully (return code 0).")
        else:
            logger.error("Minecraft backup exited with return code %d.", returncode)
    except Exception as e:
        logger.error("Error running Minecraft backup script: %s", e)

    # Backup PST data.
    logger.info("Backing up PST data...")
    try:
        backup_db_to_csv()
        logger.info("Database-to-CSV backup completed.")
    except Exception as e:
        logger.error("Error during database-to-CSV backup: %s", e)

    try:
        backup_mongo_data_as_dump()
        logger.info("MongoDB dump backup completed.")
    except Exception as e:
        logger.error("Error during MongoDB dump backup: %s", e)

    try:
        backup_state_files()
        logger.info("State files backup completed.")
    except Exception as e:
        logger.error("Error during state files backup: %s", e)

    try:
        backup_parquet_data_to_remote()
        logger.info("Parquet data remote backup completed.")
    except Exception as e:
        logger.error("Error during parquet data remote backup: %s", e)

    # Run PST cleaners.
    logger.info("Running PST cleaners...")
    try:
        clean_truncate_backtest_states()
        logger.info("Backtest states cleaned/truncated.")
    except Exception as e:
        logger.error("Error during backtest state cleanup: %s", e)

    # try:
    #     clean_truncate_echo_files()
    #     logger.info("Echo files cleaned/truncated.")
    # except Exception as e:
    #     logger.error("Error during echo file cleanup: %s", e)

    try:
        clean_truncate_log_files()
        logger.info("Log files cleaned/truncated.")
    except Exception as e:
        logger.error("Error during log file cleanup: %s", e)

if __name__ == '__main__':
    backup()
