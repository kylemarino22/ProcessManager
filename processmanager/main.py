from processmanager import Scheduler


"""
    Script that gets called by supervisor to run on reboot. Schedule file is 
    hardcoded here so that it can also be accessed by the schedulerctl cli.
    
    A schedule hash is written each time so that we determine which version
    of the schedule file we are using. This comparison is made in the cli
    list function. 
    
    This is designed to be fully managed by supervisor. This runs on system
    boot, and is intended to always be running.  
"""

SCHEDULE_FILE_PATH = '/home/kyle/ProcessManager/schedules/full_schedule.json'

if __name__ == '__main__':
    scheduler = Scheduler(SCHEDULE_FILE_PATH)
    scheduler.run()
