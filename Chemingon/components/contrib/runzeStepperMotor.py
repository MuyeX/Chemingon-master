import time
from typing import Union

from ..stdlib.component import Component
import serial
import warnings


class RunzeStepperMotor(Component):
    def __init__(self, name: str, port: str, address: int, is_public: bool = False, description: str = None,
                 baud_rate: int = 9600):
        super().__init__(name, is_public, description)
        self.serial: Union[serial.Serial, None] = None
        self.port = port
        self.address = address
        self.baud_rate = baud_rate

    @staticmethod
    def checksum_calc(message_send: list[int]):
        assert len(message_send) == 6
        message_sum = sum(message_send)
        high_checksum = message_sum >> 8
        low_checksum = message_sum - (high_checksum << 8)
        return low_checksum, high_checksum

    @staticmethod
    def checksum_verify(hex_list: list[int]):
        assert len(hex_list) == 8
        low_checksum, high_checksum = RunzeStepperMotor.checksum_calc(hex_list[:6])
        if low_checksum == hex_list[6] and high_checksum == hex_list[7]:
            return True
        else:
            return False

    def open(self):
        if not self.is_connected:
            self.log(f'Establish connection')
            self.current_op = 'Establishing connection'
            self.serial = serial.Serial(port=self.port)
            self.serial.read_all()
            self.terminate()
            self.base_state()
            self.is_connected = True
            self.current_op = None

    def close(self):
        if self.is_connected:
            if not self.query_status() == 0:
                self.terminate()
            self.serial.close()
            self.is_connected = False
            self.log('Closed')

    def _parse_received(self, message: bytes) -> tuple[int, int, bool]:
        """
        parse the received message;
        :param message: raw message received
        :return: status, params (2 bytes combined), checksum_valid
        """
        hex_list = []
        for i in message:
            hex_list.append(i)

        assert len(hex_list) == 8
        assert hex_list[0] == 0xCC, f"STX not 0xCC but {hex_list[0]}"
        assert hex_list[1] == self.address, f"ADDR not correct: {hex_list[1]} received"
        assert hex_list[5] == 0xDD, f"ETX not 0xDD but {hex_list[5]}"

        checksum_valid = RunzeStepperMotor.checksum_verify(hex_list)
        status = hex_list[2]
        params = (hex_list[3] << 8) + hex_list[4]

        return status, params, checksum_valid

    def _send_message(self, func_code: int, params: int = 0x0000) -> tuple[int, int]:
        """

        :param func_code: 1 byte
        :param params: 2 bytes
        :return:
        """
        B4 = params >> 8
        B3 = params - (B4 << 8)

        # print(f'B3 = {B3}, B4 = {B4}')

        message = [0xCC, self.address, func_code, B3, B4, 0xDD]

        B6, B7 = self.checksum_calc(message)
        message += [B6, B7]
        with self.lock:
            self.serial.write(bytes(message))
            # print('message', message)
            time.sleep(0.005)
            received = self.serial.read(8)
        status, params_received, checksum_valid = self._parse_received(received)
        # print(status)
        if not checksum_valid:
            warnings.warn("Checksum received not valid", category=RuntimeWarning)
        return status, params_received

    def _wait_until_ready(self):
        status, params_received = self._send_message(0x4A, 0x0000)
        while status != 0x00:
            self._sleep(0.05)
            status, params_received = self._send_message(0x4A, 0x0000)
            if status == 0x05:
                warnings.warn(f"Motor {self.name} blocked", category=RuntimeWarning)
            elif status == 0xFF:
                raise RuntimeError(f'Motor {self.name} unknown error')

    def base_state(self):
        self.current_op = 'Setting to base state'
        status, params_received = self._send_message(0x45, 0x0000)
        self.terminate()
        self._wait_until_ready()
        self.current_op = None

    def move_stepwise(self, steps: int, direction: str = 'CW', speed: int = 100, io_spacing: str = 'None', log: bool = True):
        """
        Turn the motor by steps;
        :param speed:
        :param steps: steps to move
        :param direction: 'CW' or 'CCW'
        :param io_spacing: 'None' or 'IO1' or 'IO2'; refer to instruction
        :param log: Logging is of when set to false
        :return:
        """
        assert direction == 'CW' or direction == 'CCW', "direction must be 'CW' or 'CCW'"
        assert io_spacing == 'None' or io_spacing == 'IO1' or io_spacing == 'IO2', "io_spacing must be 'None', 'IO1' or 'IO2'"

        if log:
            self.log(f"Moving direction: {direction}, steps: {steps}, speed: {speed}, spacing: {io_spacing}")
        self.set_speed(speed)
        self.current_op = f"Moving direction: {direction}, steps: {steps}, spacing: {io_spacing}"

        cmd = 0x40
        if direction == 'CCW':
            if io_spacing == 'None':
                cmd = 0x40
            elif io_spacing == 'IO1':
                cmd = 0x42
            elif io_spacing == 'IO2':
                cmd = 0x4C
        else:
            if io_spacing == 'None':
                cmd = 0x41
            elif io_spacing == 'IO1':
                cmd = 0x43
            elif io_spacing == 'IO2':
                cmd = 0x4D

        status, param = self._send_message(cmd, steps)
        if status == 0x02:
            raise ValueError(f'Motor {self} value error: command{cmd}, parameter{steps}')
        self._wait_until_ready()
        self.current_op = None
        return self.query_status()

    def oscillate(self, duration: float, step_size: int, speed: int = 20):
        self.current_op = 'Oscillating'
        self.log(f'Oscillate for {duration} seconds')
        start_time = time.time()
        time_delta = 0
        while time_delta < duration and not self._force_terminated:
            self.move_stepwise(step_size, direction='CW', speed=speed, log=False)
            self.move_stepwise(step_size, direction='CCW', speed=speed, log=False)
            time_delta = time.time()-start_time
        self.current_op = None

    def terminate(self):
        self.current_op = "Terminating"
        self._send_message(0x49, 0x0000)
        self._wait_until_ready()
        self.current_op = None

    def set_speed(self, rpm: int):
        self.log(f'Set speed to {rpm}')
        self._send_message(0x4B, rpm)
        self._wait_until_ready()

    def query_status(self) -> int:
        status, param = self._send_message(0x4A, 0x0000)
        return status

    def query_address(self) -> int:
        status, param = self._send_message(0x20, 0x0000)
        self.log(f'Address is {param}')
        return param

    def query_current(self) -> int:
        status, param = self._send_message(0x24, 0x0000)
        return param
