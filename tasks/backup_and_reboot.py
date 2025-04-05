#!/usr/bin/env python
import subprocess
import time
from sysproduction.backup_db_to_csv import backup_db_to_csv
from sysproduction.backup_mongo_data_as_dump import backup_mongo_data_as_dump
from sysproduction.backup_state_files import backup_state_files
from sysproduction.backup_parquet_data_to_remote import backup_parquet_data_to_remote
from sysproduction.clean_truncate_backtest_states import clean_truncate_backtest_states
from sysproduction.clean_truncate_echo_files import clean_truncate_echo_files
from sysproduction.clean_truncate_log_files import clean_truncate_log_files

# Import the Scheduler to access running programs.
import sys
sys.path.append("/home/kyle/ProcessManager/src")
from scheduler import Scheduler

def backup():
    # --- Backup Procedures ---
    # Backup Minecraft server.
    minecraft_backup_cmd = (
        "bash /home/kyle/mc-server-backups/backup-script.sh >> "
        "/home/kyle/mc-server-backups/backup_logs.txt 2>&1"
    )
    print("Backing up Minecraft server...")
    subprocess.run(minecraft_backup_cmd, shell=True)
    
    # Backup PST data.
    print("Backing up PST data...")
    backup_db_to_csv()
    backup_mongo_data_as_dump()
    backup_state_files()
    backup_parquet_data_to_remote()
    
    # Run PST cleaners.
    print("Running PST cleaners...")
    clean_truncate_backtest_states()
    clean_truncate_echo_files()
    clean_truncate_log_files()
    
    # # --- Stop Running Programs ---
    # print("Stopping all running programs...")
    # # Scheduler.instance should have been set when the scheduler was initialized.
    # if Scheduler.instance:
    #     for prog in Scheduler.instance.programs:
    #         try:
    #             prog.stop()
    #             print(f"Stopped program '{prog.name}'.")
    #         except Exception as e:
    #             print(f"Error stopping program '{prog.name}': {e}")
    # else:
    #     print("No scheduler instance found. Unable to stop programs automatically.")
    
    # # --- Reboot ---
    # print("Rebooting system...")
    # subprocess.run("sudo reboot", shell=True)

if __name__ == '__main__':
    backup()