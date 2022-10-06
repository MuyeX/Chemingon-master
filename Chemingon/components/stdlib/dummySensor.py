import math

from .sensor import Sensor
import random
import time


class DummySensor(Sensor):
    def _set_channels(self):
        self.channels = ('something1', 'something2')

    def open(self):
        self.log('Opened')

    def close(self):
        self.log('Closed')

    def update(self):
        # if 5 < time.time() - self.start_time < 6:
        #     print(f'{self.name} raising error')
        #     self._raise_error('Time > 5', fatality=False, pause=False)

        self.record({'something1': (time.time() + random.random()) % 100,
                     'something2': (time.time() + math.e ** random.random()) % 200})

    def base_state(self):
        self.log('Set to base')
