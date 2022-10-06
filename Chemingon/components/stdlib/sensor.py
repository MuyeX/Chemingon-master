import importlib

from .component import Component
import time
import pandas as pd
from threading import Lock


class Sensor(Component):
    def __init__(self, name: str, freq: int, description: str = None, keep_log: bool = True):
        super().__init__(name=name, is_public=False, description=description, keep_log=keep_log)
        self.filename = None
        self.time_str = None
        self.freq = freq
        self.start_time = None
        self.channels: tuple = ('default channel',)
        self._set_channels()
        self.interval = float(1.0 / float(self.freq))

        self._stop = False

        self.directory = None
        self.pandas_lock = Lock()

        tmp_channel_dict = {'time': []}
        for i in self.channels:
            tmp_channel_dict[i] = []

        self._data: pd.DataFrame = pd.DataFrame(tmp_channel_dict)

    def save_start_time(self, start_time: float, directory: str):
        self.start_time = start_time
        self.directory = directory
        self.time_str = time.strftime('%d%h%y_%H%M%S', time.localtime(self.start_time))
        self.filename = f"{self.directory}/{self.name}_{self.time_str}.csv"
        self.log(f"Sensor {self.name}: data will be saved as {self.filename}")

    def base_state(self):
        raise NotImplementedError(f'Base state undefined for device {self}!')

    def open(self):
        """Establish the connection"""
        raise NotImplementedError(f"Open method not implemented the device {self}!")

    def close(self):
        """Close the connection"""
        raise NotImplementedError(f"Close method not implemented for device {self}!")

    def _set_channels(self):
        """
        Must be implemented. Each channel represents one set of data and correspond to a graph;
        self.channels: names of the channels e.g. ('temperature', 'pressure')
        """
        raise NotImplementedError(f"self.channels must be defined by using the _set_channels method")
        # example: self.channels = ('temperature', 'pressure')

    def update(self):
        """Update the date, using self.record. """
        raise NotImplementedError(f'Update method not implemented for sensor {self}')

    def record(self, data: dict):
        for i in data:
            assert i in self.channels, f'Sensor {self}: Value {i} is not declared in self.channels {self.channels}'

        timedelta = float(time.time() - self.start_time)
        data['time'] = timedelta
        with self.pandas_lock:
            self.data.loc[len(self.data)] = data

    @property
    def data(self):
        return self._data

    def terminate(self):
        self._stop = True
        self.save_data()
        self.log('Terminated and data saved')

    def save_data(self):
        with self.pandas_lock:
            self.data.to_csv(self.filename, index=False)

    @property
    def stop(self):
        return self._stop



