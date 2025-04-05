import sys
print("Python sys.path:", sys.path)

from scheduler import Scheduler

if __name__ == '__main__':
    scheduler = Scheduler('schedules/test_schedule.json', 'statuses.json')
    scheduler.run()
