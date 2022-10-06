from ..stdlib.component import Component
import time
from daqmx import NIDAQmxInstrument
from typing import Union


class OceanInsightLightSource(Component):
    def __init__(self, name: str, is_public: bool = False, description: str = None, keep_log=True,
                 serial_number=32734814):
        super().__init__(name, is_public=is_public, description=description, keep_log=keep_log)
        self.port0 = None
        self.daq: Union[None, NIDAQmxInstrument] = None
        self.model_number = 'USB-6001'
        self.serial_number = serial_number

    def base_state(self):
        self.current_op = 'Setting to base state: all lamps on, shutter closed'
        self.log('Setting to base state: all lamps on, shutter closed')

        self.deuterium_on()
        self.halogen_on()
        self.shutter_close()
        self.current_op = None

    def _wait_for_deuterium_on(self):
        while True:
            d_good = False
            for i in range(0, 4):
                d_good = d_good or self.port0.line6
                self._sleep(0.5)
            if not d_good:
                break
        return self.port0.line6

    def _wait_for_halogen_on(self):
        while self.port0.line4:
            self._sleep(0.3)
        return self.port0.line4

    def get_halogen_status(self):
        return not self.port0.line7

    def get_deuterium_status(self):
        return not self.port0.line6

    def _toggle_halogen(self):
        # Halogen Lamp (switch)
        self.port0.line1 = True
        time.sleep(0.1)
        self.port0.line1 = False

    def _toggle_deuterium(self):
        # Deuterium Lamp (switch)
        self.port0.line0 = True
        time.sleep(0.1)
        self.port0.line0 = False

    def halogen_on(self):
        self.current_op = 'Turning on halogen lamp'
        self.log('Halogen lamp on')
        if not self.get_halogen_status():
            self._toggle_halogen()
            self._wait_for_halogen_on()
        self.current_op = None
        return self.get_halogen_status()

    def deuterium_on(self):
        self.current_op = 'Turning on deuterium lamp'
        self.log('Deuterium lamp on')
        if not self.get_deuterium_status():
            self._toggle_deuterium()
            self._wait_for_deuterium_on()
        self.current_op = None
        return self.get_deuterium_status()

    def halogen_off(self):
        self.current_op = 'Turning off halogen lamp'
        self.log('Halogen lamp off')
        if self.get_halogen_status():
            self._toggle_halogen()
            self._sleep(1)
        self.current_op = None
        return self.get_halogen_status()

    def deuterium_off(self):
        self.current_op = 'Turning off deuterium lamp'
        self.log('Deuterium lamp off')
        if self.get_deuterium_status():
            self._toggle_deuterium()
            self._sleep(1)
            self.current_op = None
        return self.get_deuterium_status()

    def shutter_status(self):
        return self.port0.line5

    def shutter_open(self):
        self.current_op = 'Opening shutter'
        self.log('Open shutter')
        # shutter (T/F)
        self.port0.line4 = True
        time.sleep(0.1)
        while not self.port0.line5:
            self._sleep(0.1)
        self.current_op = None
        return self.shutter_status()

    def shutter_close(self):
        self.current_op = 'Closing shutter'
        self.log('Close shutter')
        # shutter (T/F)
        self.port0.line4 = False
        time.sleep(0.1)
        while self.port0.line5:
            self._sleep(0.1)
        self.current_op = None
        return self.shutter_status()

    def open(self):
        self.current_op = 'Opening'
        self.log('Opening')

        self.daq = NIDAQmxInstrument(serial_number=self.serial_number)
        self.port0 = self.daq.port0
        self.daq.port1.line0 = True
        self.base_state()

        self.log(f'Device info: {self.daq}')
        self.is_connected = True
        self.current_op = None

    def close(self):
        self.log('Closed')
        self.base_state()

    def terminate(self):
        pass
