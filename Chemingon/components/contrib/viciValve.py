import time
from typing import Union

from ..stdlib.component import Component
import serial


class ViciValve(Component):

    def __init__(self, name: str, port: str, valve_id: str, is_public: bool = False,
                 description: str = None,
                 baud_rate: int = 9600, ser: serial.Serial = None):
        super().__init__(name, is_public, description=description)
        self.mode = 1

        if ser is None:
            self.serial: Union[serial.Serial, None] = None
        else:
            self.serial = ser
        self.port = port
        self.id = valve_id
        self.baud_rate = baud_rate

    def open(self):
        if not self.is_connected:
            self.current_op = 'Establishing connection'
            if self.serial is None:
                self.serial = serial.Serial(port=self.port)
            self.is_connected = True
            self.current_op = None
            self.serial.read_all()
            self._sleep(0.2)
            self.mode = self.get_mode()

            self.initialise()

    def close(self):
        if self.is_connected:
            self.serial.close()
            self.is_connected = False
            self.log('Closed')

    def _send_command(self, command: str) -> str:
        send_command = f'/{self.id}{command}\r'
        with self.lock:
            self.serial.read_all()
            self.serial.write(send_command.encode('utf-8'))
            # self.log(f"Message sent: {send_command}")
            time.sleep(0.5)
            result = self.serial.read_all().decode('utf-8')

            # self.log(f'Received: {result}')

        return result

    def get_mode(self) -> int:
        result = self._send_command('AM')
        result = result.splitlines()
        return int(result[0][-1])

    def base_state(self):
        self.initialise()

    def initialise(self):
        if self.mode == 1 or self.mode == 2:
            self.goto('B')
        else:
            self.goto('1')

    def goto(self, pos: str):
        """
        Mode 1, 2: Sends the actuator to position n, where n is A or B
        Mode 3: Sends the actuator to position nn (from 1 to NP) via the shortest route
        :param pos: A or B in mode 1 or int in mode 3
        :return:
        """
        if self.mode == 1 or self.mode == 2:
            assert pos == 'A' or pos == 'B'
        else:
            assert 0 <= int(pos) <= 41

        self.log(f'Go to position {pos}')
        self.current_op = pos
        self._send_command(f'GO{pos}')
        self._sleep(0.5)
        return self.get_pos()

    def switch(self):
        self._send_command('TO')
        self._sleep(0.5)
        current_pos = self.get_pos()
        self.log(f'Switched to {current_pos}')
        return current_pos

    def set_id(self, set_id: str):
        self._send_command(f'ID{set_id}')

    def get_pos(self) -> Union[str, int]:
        result = self._send_command('CP')
        cnt = 0
        while cnt <= 10 and len(result) == 0:
            time.sleep(0.2)
            result = self._send_command('CP')
            cnt += 1
        result = result.splitlines()

        if self.mode == 1 or self.mode == 2:
            assert result[0][-1] == 'A' or result[0][-1] == 'B', f'Error: return value {result}; should be A or B'
            return result[0][-1]
        else:
            return int(result[0][1:].strip('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))

    def terminate(self):
        pass
