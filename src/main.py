import sys
print("Python sys.path:", sys.path)

from scheduler import Scheduler

if __name__ == '__main__':
    scheduler = Scheduler('schedules/full_schedule.json')
    scheduler.run()
