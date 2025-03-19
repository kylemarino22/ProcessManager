from scheduler import Scheduler

if __name__ == '__main__':
    scheduler = Scheduler('test_schedules.json', 'statuses.json')
    scheduler.run()
