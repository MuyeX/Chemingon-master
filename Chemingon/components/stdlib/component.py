import time
from queue import Queue
from typing import Union
from threading import Lock
import importlib

from loguru import logger


class Component:
    """
    A single device.
    All devices should inherit Component.
    """

    def __init__(self, name: str, is_public: bool = False, description: str = None, keep_log=True):
        self.name = name
        self._isPublic = is_public
        self.keep_log = keep_log
        self.is_connected = False
        self._force_terminated = False
        self.port: Union[None, str] = None

        self.description = description
        self.description_display = description  # display in UI
        self.current_op = None

        self.lock: Lock = Lock()  # prevent error when using serial

        if self._isPublic:
            self.taskQueue = Queue()

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.name}>"

    def __str__(self):
        return f"{self.__class__.__name__} {self.name}"

    def base_state(self):
        raise NotImplementedError(f'Base state undefined for device {self}!')

    def open(self):
        """Establish the connection"""
        raise NotImplementedError(f"Open method not implemented the device {self}!")

    def close(self):
        """Close the connection"""
        raise NotImplementedError(f"Close method not implemented for device {self}!")

    def terminate(self):
        raise NotImplementedError(f"terminate method not implemented for device {self}!")

    def btn_change_connection(self, btn):
        if self.is_connected:
            self.close()
        else:
            self.open()

    @property
    def get_port(self):
        if self.port is not None:
            return self.port
        else:
            return 'No port assigned'

    @property
    def is_public(self):
        return self._isPublic

    def log(self, message: str):
        if self.keep_log:
            logger.debug(f"Log from {'public ' if self.is_public else ''}device {self.name}: {message}")

    def force_terminate_operation(self):
        self._force_terminated = True
        try:
            self.terminate()
        except NotImplementedError as e:
            logger.error(f"Terminate method not implemented for device {self.name}: {e}")
        except Exception as e:
            logger.error(f"Log from {'public ' if self.is_public else ''}device {self.name}: Error when terminating: {e}")
        self.log(f'device {self.name} force terminated')

    def _sleep(self, seconds: float):
        """
        force termination aware version of time.sleep();
        :param seconds: time in seconds
        :return: time slept
        """
        start_time = time.time()
        while time.time() - start_time < seconds and not self._force_terminated:
            time.sleep(0.01)
        if self._force_terminated:
            raise RuntimeError(f'{self.name}: force terminated')
        return time.time() - start_time

    def update_lock(self, lock_dict: dict) -> dict:
        if self.port is not None:
            if self.port in lock_dict:
                self.lock = lock_dict[self.port]
            else:
                lock_dict[self.port] = self.lock
        return lock_dict

    def _raise_error(self, err_name: str, fatality: bool = False, pause: bool = True):
        ExperimentError = importlib.import_module('.errors', 'core').ExperimentError
        raise ExperimentError(err_name, fatality=fatality, pause=pause)

    # todo 装饰器记录current_op
