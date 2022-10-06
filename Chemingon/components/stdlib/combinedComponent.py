from .component import Component
# from ...core.apparatus import Apparatus
from typing import Union
import importlib


class CombinedComponent(Component):
    def __init__(self, name: str, is_public: bool = False, description: str = None, keep_log=True):
        super().__init__(name, is_public, description, keep_log)

        # tmp_apparatus = importlib.import_module('.apparatus', 'core')
        # Apparatus = tmp_apparatus.Apparatus
        from ...core.apparatus import Apparatus
        self._apparatus: Apparatus = Apparatus(f'Apparatus of combined component {self.name}',
                                               description=f'Apparatus of combined component {self.name}')

    def get_sensor_set(self):
        if self._apparatus is not None:
            return self._apparatus.sensors
        else:
            return set()

    # todo 自动添加
    def _add_components(self, components: Union[list[Component], Component]):
        if isinstance(components, list):
            self._apparatus.add_component_list(components)
        else:
            self._apparatus.add_component(components)

    @property
    def components(self):
        return self._apparatus.components

    def base_state(self):
        for i in self.components:
            i.base_state()

    def open(self):
        if not self.is_connected:
            self.current_op = 'Connecting'
            self.log('Connecting')
            self.is_connected = True
            for i in self.components:
                i.open()
            self.current_op = None

    def close(self):
        if self.is_connected:
            for i in self.components:
                i.close()
            self.is_connected = False

    def terminate(self):
        for i in self.components:
            i.terminate()

    def update_lock(self, lock_dict: dict) -> dict:
        for device in self.components:
            lock_dict = device.update_lock(lock_dict)
        return lock_dict
