from ..stdlib.sensor import Sensor
from typing import Union

import alicat


class AlicatPressure(Sensor):
    def __init__(self, name: str, port: str, addr: str, is_public: bool = False,
                 description: str = None):
        super().__init__(name, is_public, description=description)

        self.controller: Union[None, alicat.FlowController] = None
        self.port = port
        self.addr = addr

    def open(self):
        self.current_op = 'Establishing connection'
        self.controller = alicat.FlowController(port=self.port, address=self.addr)
        self.current_op = None
        self.is_connected = True

    def close(self):
        self.controller.close()
        self.is_connected = False

    def base_state(self):
        self.set_pressure(0.0)

    def query_setpoint(self) -> float:
        with self.lock:
            ans = self.controller.get()['setpoint']
        return ans

    def query_pressure(self) -> float:
        with self.lock:
            ans = self.controller.get()['pressure']
        return ans

    def set_pressure(self, pressure: float):
        with self.lock:
            self.controller.set_pressure(pressure)

    def update(self):
        pressure = self.query_pressure()
        setpoint = self. query_setpoint()
        self.record({'pressure': pressure, 'setpoint': setpoint})

    def _set_channels(self):
        self.channels = ('pressure', 'setpoint')
