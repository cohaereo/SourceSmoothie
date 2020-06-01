from abc import (ABC, abstractmethod)

class Mountable(ABC):
    def __init__(self, path):
        super().__init__()
    
    @abstractmethod
    def open_file(self, path):
        pass
    
    @abstractmethod
    def has_file(self, path):
        pass
    
    @abstractmethod
    def fetch_filelist(self):
        pass