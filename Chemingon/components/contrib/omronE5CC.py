from typing import Union

from ..stdlib.component import Component
import serial
import serial.tools.list_ports
from modbus_tk import modbus_rtu
import modbus_tk.defines as cst


class OmronE5CC(Component):
    def __init__(self, name: str, port: str, addr: int, baudrate: int = 9600, timeout: float = 0.5,
                 description: str = None, is_public: bool = False):
        super().__init__(name, is_public, description)
        self.master: Union[None, modbus_rtu.RtuMaster] = None
        self.port = port
        self.addr = addr
        self.baudrate = baudrate
        self.bytesize = 8
        self.parity = 'N'
        self.stopbit = 2
        self.timeout = timeout

    def open(self):
        self.master = modbus_rtu.RtuMaster(
            serial.Serial(port=self.port, baudrate=self.baudrate, bytesize=self.bytesize, parity=self.parity,
                          stopbits=self.stopbit))
        self.master.set_timeout(self.timeout)
        # 2 bytes mode

    def close(self):
        self.master.close()

    def base_state(self):
        self.controller_off()

    def read_raw_data(self, param: int):
        tmp = self.master.execute(self.addr, cst.READ_HOLDING_REGISTERS, param, 1)
        return tmp[0]

    def _convert_raw_data(self, raw_data):
        dPt = self.read_raw_data(0x2410)
        trueData = self.__com_to_true(raw_data)
        if dPt >= 128:
            trueData = trueData / 10
        trueData = trueData / (10 ** (dPt % 128))
        return trueData

    def set_temp(self, target_temp: float):
        tmp = self.master.execute(self.addr, cst.WRITE_SINGLE_REGISTER, 0x2103, output_value=int(target_temp * 10))
        result = self._convert_raw_data(tmp[1])
        print(f'Temperature set to {result}')
        return result

    def controller_on(self):
        self.master.execute(self.addr, cst.WRITE_SINGLE_REGISTER, 0xFFFF, output_value = 0x0100)

    def controller_off(self):
        self.master.execute(self.addr, cst.WRITE_SINGLE_REGISTER, 0xFFFF, output_value = 0x0101)

    def read_target_temp(self):
        tmp = self.read_raw_data(0x2103)
        return self._convert_raw_data(tmp)

    def read_measured_temp(self):
        tmp = self.read_raw_data(0x2000)
        return self._convert_raw_data(tmp)

    @staticmethod
    def __com_to_true(byte16):
        # 补码转原码
        if (byte16 & 0x8000) == 0:
            return byte16
        byte16 = byte16 ^ 0xffff
        byte16 = byte16 + 1
        result = -byte16
        return result

    @staticmethod
    def __true_to_com(byte16):
        # 原码转补码
        if byte16 >= 0:
            return byte16
        byte16 = -byte16
        byte16 = byte16 - 1
        result = byte16 ^ 0xffff
        return result
