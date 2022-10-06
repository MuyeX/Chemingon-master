from .protocol import Protocol
from typing import Union
from ..components import Component
import importlib


class ExperimentError(Exception):
    def __init__(self, name, fatality: bool = False, pause: bool = True):
        self.name = name  # error name
        self.fatality = fatality
        self.pause = pause

    def __str__(self):
        return self.name


class ErrorInfo:
    def __init__(self, error: Exception, protocol: Union[None, Protocol], fatality: bool = None,
                 device=None,
                 channel_id: int = None, pause: bool = None):
        # Component = importlib.import_module('.Component', 'components')
        self.error: Exception = error
        self.protocol: Union[None, Protocol] = protocol
        if isinstance(error, ExperimentError):
            if fatality is None:
                self.fatality = error.fatality
            else:
                self.fatality = fatality
        else:
            self.fatality = True

        if isinstance(error, ExperimentError):
            if pause is None:
                self.pause = error.pause
            else:
                self.pause = pause
        else:
            self.pause = False

        self.device: Union[Component, None] = device
        self.channel_id: Union[int, None] = channel_id

    @property
    def error_name(self) -> Union[str, None]:
        if isinstance(self.error, ExperimentError):
            return self.error.name
        else:
            return None


class ErrorHandler:
    def __init__(self):
        self.force_stop_protocol: Union[None, Protocol] = None
        self.error_protocols: dict[str, Union[Protocol, callable]] = dict()  # error name: solution protocol

    def get_solution(self, error_info: ErrorInfo) -> Union[Protocol, None, callable]:
        if error_info.error_name == 'Force stop button':
            return self.force_stop_protocol
        elif error_info.error_name not in self.error_protocols:
            return None
        else:
            return self.error_protocols[error_info.error_name]

    def add_solution(self, error_name: str, protocol: Protocol):
        if error_name in self.error_protocols:
            raise ValueError(f'Error named {error_name} defined already')
        self.error_protocols[error_name] = protocol

    def set_force_stop_protocol(self, protocol: Protocol):
        self.force_stop_protocol = protocol
