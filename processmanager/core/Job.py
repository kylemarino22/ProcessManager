

from abc import ABC, abstractmethod
from ..config import Config

class Job:
    
    def __init__(self, schedule, config: Config):
        
        self.config = config
        
        self.name = schedule.get('name')


    def 