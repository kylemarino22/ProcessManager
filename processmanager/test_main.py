import sys
print("Python sys.path:", sys.path)

from processmanager import Scheduler

if __name__ == '__main__':
    scheduler = Scheduler(
        '/home/kyle/ProcessManager/schedules/test_schedules.json'
    )
    scheduler.run()
