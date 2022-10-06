from ..stdlib.component import Component
import time
import serial
from modbus_tk import modbus_rtu
from typing import Union
import modbus_tk.defines as cst


class DiySampler(Component):
    def __init__(self, name: str, port: str, x_addr: int, y_addr: int, z_addr, is_public: bool = False,
                 description: str = None, keep_log: bool = True):
        super().__init__(name, is_public=is_public, description=description, keep_log=keep_log)
        self.master: Union[modbus_rtu.RtuMaster, None] = None

        self.port = port
        self.x_addr = x_addr
        self.y_addr = y_addr
        self.z_addr = z_addr

        self.default_v = {'x': 20, 'y': 100, 'z': 200}

        self.baud_rate = 9600
        self.parity = serial.PARITY_EVEN
        self.stop_bits = 1
        self.byte_size = 8

    def base_state(self):
        self.log(f'Home')
        self.terminate('x')
        time.sleep(0.1)
        self.terminate('y')
        time.sleep(0.1)
        self.terminate('z')
        time.sleep(0.1)
        self.moveto(0, 0, 0)

    def open(self):
        if not self.is_connected:
            self.log('Establishing connection')
            self.current_op = 'Establishing connection'
            self.master = modbus_rtu.RtuMaster(
                serial.Serial(port=self.port, baudrate=self.baud_rate, bytesize=self.byte_size, parity=self.parity,
                              stopbits=self.stop_bits))
            self.master.set_timeout(1)
            self.is_connected = True
            self.current_op = None

    def close(self):
        if self.is_connected:
            self.base_state()
            self.master.close()
            self.is_connected = False
            self.log(f'Closed')

    def _get_address(self, axis: str) -> int:
        assert axis in 'xyz' and len(axis) == 1, f'axis must be x, y, or z, but got {axis} instead'
        if axis == 'x':
            addr = self.x_addr
        elif axis == 'y':
            addr = self.y_addr
        elif axis == 'z':
            addr = self.z_addr
        else:
            raise ValueError(f'Address for axis {axis} not found')
        return addr

    def _write_movement_parameters_single(self, axis: str, velocity: int = None, acceleration: int = 10000,
                                          deceleration: int = 5000):
        addr = self._get_address(axis)
        if velocity is None:
            velocity = self.default_v[axis]

        self.log(f'Set velocity = {velocity}, acceleration = {acceleration}, deceleration = {deceleration}')
        with self.lock:
            self.master.execute(addr, cst.WRITE_SINGLE_REGISTER, 0x4600, output_value=velocity)
            self.master.execute(addr, cst.WRITE_SINGLE_REGISTER, 0x4610, output_value=acceleration)
            self.master.execute(addr, cst.WRITE_SINGLE_REGISTER, 0x4620, output_value=deceleration)

            ret_v = self.master.execute(addr, cst.READ_HOLDING_REGISTERS, 0x4600, 1)[0]
            ret_a = self.master.execute(addr, cst.READ_HOLDING_REGISTERS, 0x4610, 1)[0]
            ret_d = self.master.execute(addr, cst.READ_HOLDING_REGISTERS, 0x4620, 1)[0]
        return ret_v, ret_a, ret_d

    @staticmethod
    def _truetocom(byte16):
        # 原码转补码
        if byte16 >= 0:
            return byte16
        byte16 = -byte16
        byte16 = byte16 - 1
        result = byte16 ^ 0xffffffff
        return result

    @staticmethod
    def _comtotrue(byte16):
        # 补码转原码
        if (byte16 & 0x80000000) == 0:
            return byte16
        byte16 = byte16 ^ 0xffffffff
        byte16 = byte16 + 1
        result = -byte16
        return result

    @staticmethod
    def _split_32bit(byte32: int):
        left = byte32 >> 16
        right = byte32 - (left << 16)
        return left, right

    @staticmethod
    def _combine_32bit(left: int, right: int):
        return right + (left << 16)

    def _write_block0_single(self, axis: str, command: int, data: int):
        addr = self._get_address(axis)
        data = self._truetocom(data)
        cmd_left, cmd_right = self._split_32bit(command)
        data_left, data_right = self._split_32bit(data)
        self.master.execute(addr, cst.WRITE_MULTIPLE_REGISTERS, 0x4800,
                            output_value=[cmd_right, cmd_left, data_right, data_left])

    def query_motor_position_single(self, axis: str) -> int:
        addr = self._get_address(axis)
        result = self.master.execute(addr, cst.READ_HOLDING_REGISTERS, 0x600F, 2)
        result_combined = self._combine_32bit(result[1], result[0])
        result_combined = self._comtotrue(result_combined)
        return result_combined

    @staticmethod
    def _calc_motor_to_distance(axis: str, motor_pos: int) -> float:
        if axis == 'x':
            return motor_pos / 10000 * 140
        else:
            return motor_pos / 1000

    @staticmethod
    def _calc_distance_to_motor(axis: str, distance: int) -> int:
        if axis == 'x':
            return int(distance * 10000 / 140)
        else:
            return int(distance * 1000)

    def query_axis_position_single(self, axis: str):
        motor_pos = self.query_motor_position_single(axis)
        time.sleep(0.01)
        return self._calc_motor_to_distance(axis, motor_pos)

    def _srv_on(self, axis: str, pos: bool = True):
        addr = self._get_address(axis)
        self.master.execute(addr, cst.WRITE_SINGLE_COIL, 0x60, output_value=int(pos))

    def _set_block_num(self, axis: str, block_num: int):
        addr = self._get_address(axis)
        self.master.execute(addr, cst.WRITE_SINGLE_REGISTER, 0x4414, output_value=block_num)

    def _stb_on(self, axis):
        addr = self._get_address(axis)
        self.master.execute(addr, cst.WRITE_MULTIPLE_COILS, 0x120, output_value=[1, 0, 0, 0, 0])
        self.master.execute(addr, cst.WRITE_MULTIPLE_COILS, 0x120, output_value=[0, 0, 0, 0, 0])

    def _is_moving(self, axis: str):
        addr = self._get_address(axis)
        result = self.master.execute(addr, cst.READ_COILS, 0x102, 2)
        time.sleep(0.01)
        # print(result)
        neg, pos = result
        moving = bool(neg) or bool(pos)
        return moving

    def _start_movement_abs_single(self, axis: str, dist: int, velocity: int = None, acceleration: int = 5000,
                                   deceleration: int = 5000):
        self._srv_on(axis)
        self._set_block_num(axis, 0)
        self._write_movement_parameters_single(axis, velocity=velocity, acceleration=acceleration,
                                               deceleration=deceleration)
        self._write_block0_single(axis, command=0x02000000, data=self._calc_distance_to_motor(axis, dist))
        self._stb_on(axis)

    def terminate(self, axis: str):
        addr = self._get_address(axis)
        self.log(f'Terminate {axis} axis')
        self.current_op = f'Terminating {axis} axis'

        self.master.execute(addr, cst.WRITE_MULTIPLE_COILS, 0x120, output_value=[0, 0, 0, 1, 0])
        time.sleep(0.01)
        self.master.execute(addr, cst.WRITE_MULTIPLE_COILS, 0x120, output_value=[0, 0, 0, 0, 0])
        self._wait_until_stop()
        self.current_op = None

    def _wait_until_stop(self):
        is_moving = True
        while is_moving:
            x_mov = self._is_moving('x')
            time.sleep(0.01)
            y_mov = self._is_moving('y')
            time.sleep(0.01)
            z_mov = self._is_moving('z')
            time.sleep(0.01)
            # print(x_mov, y_mov, z_mov)
            is_moving = x_mov or y_mov or z_mov
            self._sleep(0.1)

    def moveto(self, x_pos: int = None, y_pos: int = None, z_pos: int = None):
        self.log(f'Moving to x {x_pos}mm, y {y_pos}mm, z {z_pos}mm')
        self.current_op = f'Moving to x {x_pos}mm, y {y_pos}mm, z {z_pos}mm'
        if x_pos is not None:
            self._start_movement_abs_single('x', x_pos)
            time.sleep(0.1)
        if y_pos is not None:
            self._start_movement_abs_single('y', y_pos)
            time.sleep(0.1)
        if z_pos is not None:
            self._start_movement_abs_single('z', z_pos)
            time.sleep(0.1)

        self._wait_until_stop()

        x_pos_curr = self.query_axis_position_single('x')
        time.sleep(0.01)
        y_pos_curr = self.query_axis_position_single('y')
        time.sleep(0.01)
        z_pos_curr = self.query_axis_position_single('z')
        time.sleep(0.01)

        self.current_op = None

        return x_pos_curr, y_pos_curr, z_pos_curr
