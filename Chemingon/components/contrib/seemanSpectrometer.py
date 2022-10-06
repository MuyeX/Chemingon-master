import warnings

import numpy as np
import time
from ..stdlib import Sensor
import usb.core
import usb.util
import struct
from typing import Union
import array
import pandas as pd


class SeemanSpectrometer(Sensor):
    def __init__(self, name: str, freq: int, description: str = None, keep_log: bool = True,
                 record_wavelength: list = None, integration_time=10):

        self.full_data = []
        self.full_data_time = []

        self._READ_ENDPOINT = 0x81
        self._WRITE_ENDPOINT = 0x02
        self.dev: Union[None, usb.core.Device] = None
        self.record_wavelength = record_wavelength
        self.record_wavelength_idx = None
        self.record_wavelength_actual = None
        self.integration_time = integration_time

        super().__init__(name, freq, description=description, keep_log=keep_log)

    def open(self):
        self.dev = usb.core.find(idVendor=0x8888, idProduct=0x8888)  # find Spectrometer device
        if self.dev is None:
            raise ValueError('Spectrometer Device not found')
        # set the active configuration. With no arguments, the first configuration will be the active one
        self.dev.set_configuration()
        self._get_pixel_number()
        self._get_serial_number()
        self._get_wavelengths_array()

        self.is_connected = True
        self.log(f'Opened, recording {self.record_wavelength_actual}, device serial {self.SN}')

    def _get_pixel_number(self):
        rtn = self.dev.write(self._WRITE_ENDPOINT, b'\x30', 1000)
        time.sleep(0.01)
        buffer = self.dev.read(self._READ_ENDPOINT, 2, 1000)
        self.PIXELS = buffer[0] * 256 + buffer[1]
        return self.PIXELS

    def _get_serial_number(self):
        rtn = self.dev.write(self._WRITE_ENDPOINT, '<0.device.sn.get/>', 1000)
        # rtn = dev.write(WRITE_ENDPOINT,b'\x40',1000)
        buffer = self.dev.read(self._READ_ENDPOINT, 64, 2000)
        tmp_sn = ()
        for i in range(64):
            if buffer[i] == 0x00:
                break
            tmp_sn += struct.unpack('b', buffer[i:i + 1])  # 不能用'c"类型
        ls2 = [chr(i) for i in tmp_sn]  # chr(97) 显示为 a  而 str(97) 显示为 97
        str_sn = "Serial Number: " + ''.join(ls2)
        self.SN = str_sn
        return self.SN

    def _get_wavelengths_array(self) -> np.array:
        rtn = self.dev.write(self._WRITE_ENDPOINT, '<0.wavelength.coeffs.get/>', 1000)
        # rtn = dev.write(WRITE_ENDPOINT,b'\x51\x1E\x30',2000) # wavelength Coeffs
        buffer = self.dev.read(self._READ_ENDPOINT, 64, 2000)
        # print("Wavelength Calibration Coefficients: ")
        dCoefficients = ()
        for i in range(6):
            dCoefficients += struct.unpack('d', buffer[i * 8:i * 8 + 8])  # double
        # print(dCoefficients)
        self._dCoefficients = list(dCoefficients)

        fWavelength = array.array('f', [0] * self.PIXELS)

        for i in range(self.PIXELS):
            fWavelength[i] = dCoefficients[0] + dCoefficients[1] * i + dCoefficients[2] * i * i + dCoefficients[3] * (
                    i ** 3) + dCoefficients[4] * (i ** 4) + dCoefficients[5] * (i ** 5)
        self._Wavelength: np.array = np.array(fWavelength)

        self.record_wavelength_idx = []
        self.record_wavelength_actual = []
        for i in self.record_wavelength:
            idx, val = self._find_nearest(self._Wavelength, i)
            self.record_wavelength_idx.append(idx)
            self.record_wavelength_actual.append(val)
            if abs(i - val) > 1:
                warnings.warn(f'Large difference between set value {i} and found value {val}')
        assert len(self.record_wavelength_idx) == len(self.record_wavelength)

        return self._Wavelength

    def read_intensities(self) -> np.array:
        integration_time_ms = self.integration_time
        f_ms = float(integration_time_ms)  # 10ms Integration Time in ms.
        n_intensity = array.array('H', [0] * self.PIXELS)  # H = u16

        m = 1
        strCMD = "<0.intensity.read v='%.3f'/>" % f_ms
        rtn = self.dev.write(self._WRITE_ENDPOINT, strCMD, 1000)  # Read Intensity
        if (rtn < 5):
            print("Read Intensity Failed. #1")
            return
        try:
            buffer = array.array('B', [0] * self.PIXELS * 2)
            lens_read = self.dev.read(self._READ_ENDPOINT, buffer, int(f_ms) * m + 2000)
            # print("USB Read: %d Bytes" % lens_read)
            if (lens_read != self.PIXELS * 2):
                print("Read Intensity Failed. #2")
                return 0
            for i in range(self.PIXELS):
                n_intensity[i] = buffer[i * 2 + 1] * 256 + buffer[i * 2]
        except Exception as e:
            self.dev.reset()
            print(f"Device Reset! {e}")

        return np.array(n_intensity)

    @property
    def wavelength(self):
        return self._Wavelength

    def base_state(self):
        pass

    def close(self):
        self.log('Close')
        self.dev.reset()

    def _set_channels(self):
        tmp_list = []
        if self.record_wavelength is not None:
            for i in self.record_wavelength:
                tmp_list.append(str(i))
            self.channels = tuple(tmp_list)

    def update(self):
        intensities = self.read_intensities()
        tmp_dict = dict()

        for i in range(0, len(self.record_wavelength)):
            idx = self.record_wavelength_idx[i]
            tmp_dict[str(self.record_wavelength[i])] = sum(intensities[idx - 1:idx + 2]) / 3
        self.record(tmp_dict)

        timedelta = float(time.time() - self.start_time)
        self.full_data_time.append(timedelta)
        self.full_data.append(intensities)

    def save_data(self):
        with self.pandas_lock:
            self.data.to_csv(self.filename, index=False)

        # tmp_data_dict = {'time': self.full_data_time}
        # for i in range(len(self._Wavelength)):
        #    tmp_data_dict[self._Wavelength[i]] = np.array(self.full_data)[:, i].tolist()
        # try:
        #    tmp_pd = pd.DataFrame(tmp_data_dict)
        #    tmp_pd.to_csv(self.filename[:-4] + '_Full.csv', inde00x=False)
        # except ValueError as e:
        #    warnings.warn(str(e))
        np.savetxt(self.filename[:-4] + '_Full_time.csv', np.array(self.full_data_time), fmt='%.3f', delimiter=',')
        np.savetxt(self.filename[:-4] + '_Full_spec.csv', np.array(self.full_data), fmt='%.3f', delimiter=',')

    @staticmethod
    def _find_nearest(arr, value: Union[int, float]) -> tuple[int, np.array]:
        arr: np.array = np.asarray(arr)
        idx = (np.abs(arr - value)).argmin()
        return idx, arr[idx]
