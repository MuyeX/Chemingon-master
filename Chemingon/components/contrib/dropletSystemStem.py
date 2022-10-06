import time
import warnings

from ..stdlib.combinedComponent import CombinedComponent
from .cavroXCaliburPump import CavroXCaliburPump
from .viciValve import ViciValve
import serial
from typing import Union


class DropletSystemStem(CombinedComponent):
    def __init__(self, name: str, pump_port: str, valve_port: str, is_public: bool, description: str = None,
                 keep_log: bool = True, valve_ser: Union[None, serial.Serial] = None):
        super().__init__(name, is_public, description, keep_log)
        if valve_ser is None:
            self.valve_serial = serial.Serial(port=valve_port)
        else:
            self.valve_serial = valve_ser
        self.valveA = ViciValve('Stem valve A', port=valve_port, valve_id='A', description='Channel selection valve A', ser=self.valve_serial)
        self.valveB = ViciValve('Stem valve B', port=valve_port, valve_id='B', description='Channel selection valve B', ser=self.valve_serial)
        self.valve1 = ViciValve('Gas valve', port=valve_port, valve_id='1', description='stem valve 1', ser=self.valve_serial)

        self.pump_s1 = CavroXCaliburPump('Stem pump sample1', port=pump_port, address_switch=2, syringe_size=1000)
        self.pump_s2 = CavroXCaliburPump('Stem pump sample 2', port=pump_port, address_switch=3, syringe_size=1000)
        self.pump_gas = CavroXCaliburPump('Stem pump gas', port=pump_port, address_switch=1, syringe_size=1000)  # gas
        self.pump_rinse = CavroXCaliburPump('Stem pump rinse', port=pump_port, address_switch=4, syringe_size=5000)
        self.pump_water = CavroXCaliburPump('Stem pump water', port=pump_port, address_switch=0, syringe_size=1000)

        self._add_components([self.valveA, self.valveB, self.valve1, self.pump_rinse, self.pump_gas, self.pump_s1, self.pump_water, self.pump_s2])

    def wait_all_pumps(self):
        for i in self._apparatus.components:
            if isinstance(i, CavroXCaliburPump):
                i.wait_until_ready()

    def pickup_all(self):

        def wait_all():
            self.pump_rinse.wait_until_ready()
            self.pump_s2.wait_until_ready()
            self.pump_s1.wait_until_ready()
            self.pump_gas.wait_until_ready()
            self.pump_water.wait_until_ready()

        self.current_op = 'Pick up all'
        # todo remove bubbles
        self.pump_s1.rel_pickup(valve_pos='input', rel_pos=1000, top_speed=100, wait=False)
        self.pump_rinse.rel_pickup(valve_pos='input', rel_pos=1000, top_speed=100, wait=False)
        self.pump_water.rel_pickup(valve_pos='input', rel_pos=1000, top_speed=100, wait=False)
        self.pump_gas.rel_pickup(valve_pos='bypass', rel_pos=1000, top_speed=100, wait=False)
        self.pump_s2.rel_pickup(valve_pos='input', rel_pos=1000, top_speed=100, wait=False)
        wait_all()

        self.pump_s1.abs_position(valve_pos='input', abs_pos=0, top_speed=100, wait=False)
        self.pump_rinse.abs_position(valve_pos='input', abs_pos=0, top_speed=100, wait=False)
        self.pump_gas.abs_position(valve_pos='bypass', abs_pos=0, top_speed=100, wait=False)
        self.pump_water.abs_position(valve_pos='input', abs_pos=0, top_speed=100, wait=False)
        self.pump_s2.abs_position(valve_pos='input', abs_pos=0, top_speed=100, wait=False)
        wait_all()

        self.pump_s1.rel_pickup(valve_pos='input', rel_pos=1000, top_speed=100, wait=False)
        self.pump_rinse.rel_pickup(valve_pos='input', rel_pos=2100, top_speed=100, wait=False)
        self.pump_gas.rel_pickup(valve_pos='bypass', rel_pos=50, top_speed=100, wait=False)
        self.pump_water.rel_pickup(valve_pos='input', rel_pos=1000, top_speed=100, wait=False)
        self.pump_s2.rel_pickup(valve_pos='input', rel_pos=500, top_speed=100, wait=False)
        wait_all()

        self.pump_s1.rel_dispense(valve_pos='input', rel_pos=50, top_speed=100, wait=False)
        self.pump_rinse.rel_dispense(valve_pos='input', rel_pos=100, top_speed=100, wait=False)
        self.valve1.goto('B')
        self.pump_gas.rel_pickup(valve_pos='input', rel_pos=20, top_speed=100, wait=False)
        self.pump_water.rel_dispense(valve_pos='input', rel_pos=50, top_speed=100, wait=False)
        self.pump_s2.rel_dispense(valve_pos='input', rel_pos=50, top_speed=100, wait=False)
        wait_all()

        self.current_op = None

    def fill_tubes_init(self):
        self.current_op = f'filling tubes'
        self.log('fill tubes')
        self.select_channel(10)
        self.pump_s1.rel_dispense(valve_pos='output', rel_pos=250, top_speed=10)
        self.pump_rinse.rel_dispense(valve_pos='output', rel_pos=250, top_speed=10)
        self.pump_s2.rel_dispense(valve_pos='output', rel_pos=250, top_speed=10)
        self.pump_water.rel_dispense(valve_pos='output', rel_pos=250, top_speed=10)
        self.propel_gas(700, speed=20)
        self.propel_gas(700, speed=20)
        # self.propel_gas(500, speed=20)
        self.blow_gas(3)
        self._sleep(2)
        self.blow_gas(5)
        self.current_op = None

    def select_channel(self, channel: int):
        """
        select channel;
        :param channel: channel to be switched to; Bypass if 0 (default)
        :return: current channel
        """
        tmp_op = self.current_op
        self.current_op = f'Switching channel to {channel}'
        self.description = f'Current channel: {channel}'
        a_pos = self.valveA.goto(str(channel))
        time.sleep(0.1)
        b_pos = self.valveB.goto(str(channel))
        if a_pos != b_pos:
            warnings.warn('Channel selection valves not at the same position!')
        self.current_op = tmp_op
        self.log(f'Channel {channel} selected')
        return a_pos

    def rinse(self, channel: int):
        tmp_op = self.current_op
        self.current_op = f'Rinsing channel {channel}'
        self.log(f'Rinsing channel {channel}')

        self.select_channel(channel)
        self.pump_rinse.rel_dispense(valve_pos='output', rel_pos=50, top_speed=10)
        self.propel_gas(700, speed=40)
        self.propel_gas(700, speed=40)
        self.blow_gas(3)
        self._sleep(2)
        self.blow_gas(3)

        self.select_channel(10)
        self.current_op = tmp_op

    def blow_gas(self, duration: int = 3, channel: int = None):
        tmp_op = self.current_op
        self.current_op = f'Blowing gas in channel {channel}: {duration} seconds'
        self.log(f'Blowing gas in channel {channel}: {duration} seconds')
        if channel is not None:
            self.select_channel(channel)

        self.valve1.goto('A')
        time.sleep(duration)
        self.valve1.goto('B')

        if channel is not None:
            self.select_channel(10)
        self.current_op = tmp_op

    def propel_gas(self, volume: int, channel: int = None, speed: int = 8):
        tmp_op = self.current_op
        self.current_op = f'Propelling gas in channel {channel}: {volume}ul'
        self.log(f'Propelling gas in channel {channel}: {volume}ul')

        if channel is not None:
            self.select_channel(channel)

        self.valve1.goto('B')
        self._sleep(1)
        self.pump_gas.rel_pickup(valve_pos='input', rel_pos=volume, top_speed=100)
        self._sleep(2)
        self.pump_gas.switch_valve(valve_pos='bypass')
        self._sleep(1)
        self.pump_gas.rel_dispense(valve_pos='output', rel_pos=volume, top_speed=speed)
        self.pump_gas.switch_valve('bypass')

        if channel is not None:
            self.select_channel(10)
        self.current_op = tmp_op

    def prep_droplet(self, channel: int, drop1_vol: int = 15, drop2_vol: int = 15, gas_volume: int = 200, gas_speed = 5):
        self.current_op = f'Preparing droplet in channel {channel}'
        self.log(f'Preparing droplet in channel {channel}')

        self.select_channel(channel)
        self.current_op = f'Preparing droplet in channel {channel}'

        time.sleep(0.1)
        # self.current_op = f'Preparing droplet in channel {channel}: dispensing pump1'
        self.pump_s2.rel_dispense(valve_pos='output', rel_pos=drop2_vol, top_speed=3, wait=False)
        time.sleep(1)
        self.pump_s1.rel_dispense(valve_pos='output', rel_pos=drop1_vol, top_speed=3, wait=False)
        # self.current_op = f'Preparing droplet in channel {channel}: dispensing pump2'
        # self.pump2.rel_dispense(valve_pos='output', rel_pos=drop2_vol, top_speed=3)

        self.wait_all_pumps()
        self._sleep(10)
        self.propel_gas(volume=gas_volume, speed=gas_speed)

        self.select_channel(10)
        self.current_op = None

    def propel_water(self, volume = 30, gas_volume = 400):
        self.current_op = 'Propelling water'
        self.log('Propel water')
        self.pump_water.rel_dispense(valve_pos='output', rel_pos=volume, top_speed=3)
        self._sleep(1)
        self.propel_gas(volume=gas_volume)
        self.current_op = None

    def analysis(self, channel: int):
        self.select_channel(channel)
        self.propel_gas(volume=100)
        # todo not completed

    def open(self, init: bool = True):
        if not self.is_connected:
            self.current_op = 'Connecting'
            self.log('Connecting')
            self.is_connected = True
            for i in self.components:
                if isinstance(i, CavroXCaliburPump):
                    i.open(init=False)
                    if init:
                        i.initialise(wait=False)
                else:
                    i.open()

            for i in self.components:
                if isinstance(i, CavroXCaliburPump):
                    i.wait_until_ready()
            self.current_op = None
            self.valve1.goto('B')

    def finishing(self, top_speed: int = 100):
        self.current_op = 'Finishing'
        self.log('Finishing')

        self.select_channel(10)
        self.pump_s1.abs_position(valve_pos='input', abs_pos=0, top_speed=top_speed, wait=False)
        # self.pump2.abs_position(valve_pos='output', abs_pos=0, top_speed=top_speed, wait=False)
        self.pump_rinse.abs_position(valve_pos='input', abs_pos=0, top_speed=top_speed, wait=False)
        self.pump_s2.abs_position(valve_pos='input', abs_pos=0, top_speed=top_speed, wait=False)
        self.pump_water.abs_position(valve_pos='input', abs_pos=0, top_speed=top_speed, wait=False)
        self.wait_all_pumps()

        self._sleep(1)
        # self.propel_gas(300, speed=20)
        self.pump_gas.abs_position(valve_pos='bypass', abs_pos=0, top_speed=top_speed)

        self.blow_gas(3)
        self._sleep(1)
        self.blow_gas(3)

        self.current_op = None
