import time
from typing import Union

from ..stdlib.component import Component
import pyvisa


class CavroXCaliburPump(Component):
    def __init__(self, name: str, port: str, address_switch: int, syringe_size: int, is_public: bool = False,
                 description: str = None,
                 baud_rate: int = 9600):

        super().__init__(name, is_public=is_public, description=description)
        self.port = port
        self.baud_rate = baud_rate
        self.syringe_size = syringe_size  # ul

        self.visa_rm: pyvisa.highlevel.ResourceManager = pyvisa.ResourceManager()
        self.visa_port = None
        self.visa_instrument: Union[pyvisa.resources.serial.SerialInstrument, None] = None
        self.pump_address = address_switch  # this address +1 gives the ascii address

    def base_state(self):
        self.initialise()
        self._send_command('Q')
        pass

    def _send_command(self, command: str) -> tuple:
        send_command = f'/{str(self.pump_address + 1)}{command}\r'
        # self.log(f'Message sent: {send_command}')
        with self.lock:
            result = self.visa_instrument.query(send_command, delay=0.01)
        status, err_code, data = self._parse_response(result)
        # self.log(f'Received: status = {status}, error code = {err_code}, data = {data}')
        if not err_code == 0:
            raise RuntimeError(f'Error when executing [{send_command}]: Error Code {err_code}')
        return status, err_code, data

    def wait_until_ready(self):
        time.sleep(0.1)
        ready, err_code, data = self._send_command('Q')
        while not ready:
            self._sleep(0.2)
            ready, err_code, data = self._send_command('Q')

    @staticmethod
    def _parse_response(response: str) -> tuple:
        response_stripped = response.rstrip('\r\n\x03').lstrip('/0')

        str_err = response_stripped[0]
        data: str = response_stripped[1:]

        status: bool = bool(int((ord(str_err) - 0b1000000) / 0b100000))  # true: ready; false: busy
        err_code: int = int((ord(str_err) - 0b1000000) % 0b100000)

        return status, err_code, data

    def initialise(self, polarity: str = 'CW', force: int = 0, input_port: int = 0, output_port: int = 0, wait: bool = True):
        # initialise plunger and valve
        self.current_op = 'Initialising'
        self.log(f'Initialising: polarity = {polarity}, force = {force}, input_port = {input_port}, output_port = {output_port}')
        cmd_code = 'Z'
        n1 = str(force)
        n2 = str(input_port)
        n3 = str(output_port)

        if polarity == 'CCW':
            cmd_code = 'Y'

        self._send_command(f"{cmd_code}{n1},{n2},{n3}R")
        if wait:
            self.wait_until_ready()
        self.current_op = None

    def query_abs_position(self):
        """
        The [?] command
        :return: the absolute position of the plunger in increments [0..3000], [0..24000 in fine positioning mode].
        """
        status, error_code, data = self._send_command("?")
        self.log(f'Current absolute plunger position is {data}')
        return int(data)

    def query_valve_pos(self) -> str:
        """
        :return: The [?6] command reports the valve position in mnemonics (i = input, o = output, and b = bypass)
                    for non-distribution valves.
                For distribution valves, the [?6] command reports numerical values 1...X,
                    where X is the number of distribution valve ports.
        """
        status, error_code, data = self._send_command("?6")
        self.log(f'Current valve position is {data}')
        return data

    @staticmethod
    def _convert_val_pos(valve_pos: str) -> str:
        """
        ;
        :param valve_pos: 'input' or 'output' or 'bypass'
        :return: 'I' or 'O'
        """
        if valve_pos == 'input':
            valve_cmd = 'I'
        elif valve_pos == 'output':
            valve_cmd = 'O'
        elif valve_pos == 'bypass':
            valve_cmd = 'B'
        else:
            raise ValueError("valve_pos must be 'input' or 'output'. ")
        return valve_cmd

    def abs_position_increments(self, valve_pos: str, abs_pos: int, top_speed: int = 1400, wait: bool = True) -> int:
        """
        ;
        :param wait: wait until finished
        :param valve_pos: "input" or "output" or 'bypass'
        :param abs_pos: absolute position to move the plunger <n> = 0..3000 in standard mode
                        and 0..24000 in fine positioning mode
        :param top_speed: The [V] command sets the top speed in pulses/second 5-6000. 1400 by default
        :return: current position
        """
        self.log(f'Move to position {str(abs_pos)}; valve: {valve_pos}')
        self.current_op = f'Move to position {str(abs_pos)}; valve: {valve_pos}'
        valve_cmd = self._convert_val_pos(valve_pos)
        self._send_command(f"V{str(top_speed)}{valve_cmd}A{str(abs_pos)}R")
        if wait:
            self.wait_until_ready()

        current_pos = self.query_abs_position()
        self.current_op = None
        return current_pos

    def abs_position(self, valve_pos: str, abs_pos: int, top_speed: int = None, wait: bool = True) -> int:
        """
        ;
        :param valve_pos:  "input" or "output" or 'bypass'
        :param abs_pos: absolute position in ul
        :param top_speed: top speed in ul/s
        :return: current position in ul
        """
        self.log(f'Move to {abs_pos}ul')
        abs_pos_converted = int(abs_pos * 3000 / self.syringe_size)

        if top_speed is None:
            result = self.abs_position_increments(valve_pos, abs_pos_converted, wait=wait)
        else:
            top_speed_converted = int(top_speed * 6000 / self.syringe_size)
            result = self.abs_position_increments(valve_pos, abs_pos_converted, top_speed_converted, wait=wait)

        return int(result * self.syringe_size / 3000)  # return position in ul

    def rel_pickup_increments(self, valve_pos: str, rel_pos: int, top_speed: int = 1400, wait: bool = True) -> int:
        """
        ;
        :param wait: wait until finished
        :param valve_pos: "input" or "output" or 'bypass'
        :param rel_pos: The [P] command moves the plunger down the number of increments commanded.
                            The new absolute position is the previous position plus <n>,
                            where<n> = 0..3000 in standard mode and 0..24000 in fine positioning mode
        :param top_speed: The [V] command sets the top speed in pulses/second 5-6000. 1400 by default
        :return: current position
        """
        self.log(f'Relative picup {rel_pos}; valve: {valve_pos}')
        self.current_op = f'Relative picup {rel_pos}; valve: {valve_pos}'
        valve_cmd = self._convert_val_pos(valve_pos)

        self._send_command(f"V{str(top_speed)}{valve_cmd}P{str(rel_pos)}R")
        if wait:
            self.wait_until_ready()

        current_pos = self.query_abs_position()
        self.current_op = None
        return current_pos

    def rel_pickup(self, valve_pos: str, rel_pos: int, top_speed: int = None, wait: bool = True) -> int:
        """
        ;
        :param wait: wait until finished
        :param valve_pos: "input" or "output" or 'bypass'
        :param rel_pos: relative position in ul
        :param top_speed: top speed in ul/s
        :return: current position in ul
        """
        self.log(f'Pickup {rel_pos}ul')
        rel_pos_converted = int(rel_pos * 3000 / self.syringe_size)
        if top_speed is None:
            result = self.rel_pickup_increments(valve_pos, rel_pos_converted, wait=wait)
        else:
            top_speed_converted = int(top_speed * 6000 / self.syringe_size)
            result = self.rel_pickup_increments(valve_pos, rel_pos_converted, top_speed_converted, wait=wait)
        return int(result * self.syringe_size / 3000)

    def rel_dispense_increments(self, valve_pos: str, rel_pos: int, top_speed: int = 1400, wait: bool = True) -> int:
        """
        ;
        :param wait: wait until finished
        :param valve_pos: "input" or "output"
        :param rel_pos: The [D] command moves the plunger up the number of increments commanded.
                            The new absolute position is the previous position plus <n>,
                            where<n> = 0..3000 in standard mode and 0..24000 in fine positioning mode
        :param top_speed: The [V] command sets the top speed in pulses/second 5-6000. 1400 by default
        :return: current position
        """
        self.log(f'Relative dispense {rel_pos}; valve: {valve_pos}')
        self.current_op = f'Relative dispense {rel_pos}; valve: {valve_pos}'
        valve_cmd = self._convert_val_pos(valve_pos)

        self._send_command(f"V{str(top_speed)}{valve_cmd}D{str(rel_pos)}R")
        if wait:
            self.wait_until_ready()

        current_pos = self.query_abs_position()
        self.current_op = None
        return current_pos

    def rel_dispense(self, valve_pos: str, rel_pos: int, top_speed: int = None, wait: bool = True) -> int:
        """
        ;
        :param wait: wait until finished
        :param valve_pos: "input" or "output" or 'bypass'
        :param rel_pos: relative position in ul
        :param top_speed: top speed in ul/s
        :return: current position in ul
        """
        self.log(f'Dispense {rel_pos}ul')
        rel_pos_converted = int(rel_pos * 3000 / self.syringe_size)
        if top_speed is None:
            result = self.rel_dispense_increments(valve_pos, rel_pos_converted, wait=wait)
        else:
            top_speed_converted = int(top_speed * 6000 / self.syringe_size)
            result = self.rel_dispense_increments(valve_pos, rel_pos_converted, top_speed_converted, wait=wait)
        return int(result * self.syringe_size / 3000)

    def switch_valve(self, valve_pos: str) -> str:
        """
        The [?6] command reports the valve position in mnemonics (i = input, o = output, and b = bypass)
            for non-distribution valves.
        For distribution valves, the [?6] command reports numerical values 1...X,
            where X is the number of distribution valve ports;
        :param valve_pos: 'input' or 'output' or 'bypass'
        :return: i, o, b for non-distribution valves OR 1-x for distribution valve ports
        """
        self.log(f'Switch valve to position {valve_pos}')
        self.current_op = f'Switch valve to position {valve_pos}'
        valve_cmd = self._convert_val_pos(valve_pos)
        self._send_command(f"{valve_cmd}R")
        self.wait_until_ready()
        current_valve_pos = self.query_valve_pos()
        self.current_op = None
        return current_valve_pos

    def terminate(self):
        self._send_command("TR")
        self.current_op = 'Terminated'
        self.log(f'Terminated')

    def open(self, init: bool = True):
        if not self.is_connected:
            self.log('Establish connection')
            self.current_op = 'Establishing connection'

            resource_list = self.visa_rm.list_resources()
            for i in resource_list:
                if self.port in i:
                    self.visa_port = i
                    break
            if self.visa_rm is None:
                raise RuntimeError(f'Not found visa resource on {self.port}')
            # print(self.visa_rm)
            self.visa_instrument = self.visa_rm.open_resource(self.visa_port)
            self.is_connected = True
            self.current_op = None

            if init:
                self.initialise()

    def close(self):
        if self.is_connected:
            self.visa_rm.close()
            self.is_connected = False
            self.log('Closed')
