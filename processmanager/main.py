from processmanager import Scheduler
from processmanager.config import config
import logging

"""
    Script that gets called by supervisor to run on reboot. Schedule file is 
    hardcoded here so that it can also be accessed by the schedulerctl cli.
    
    A schedule hash is written each time so that we determine which version
    of the schedule file we are using. This comparison is made in the cli
    list function. 
    
    This is designed to be fully managed by supervisor. This runs on system
    boot, and is intended to always be running.  
    
    Change config in config.py or else schedulerctl will not match.
"""


if __name__ == '__main__':
    scheduler = Scheduler(config, logging.INFO)
    scheduler.run()

