from ..components.stdlib import component
from ..components.stdlib.sensor import Sensor
# from operation import Operation, VirtualOperation


class Apparatus:
    """
    Define the experimental set-up used.
    """

    def __init__(self, name: str, description: str = None):
        self.name = name
        self.description = description
        self.components: set[component.Component] = set()
        self.publicComponents: set[component.Component] = set()
        self.sensors: set[Sensor] = set()
        self.virtual_devices = set()

        self._lock_dict = dict()

    def __repr__(self):
        return f"<Apparatus {self.name}>"

    def __str__(self):
        return f"Apparatus {self.name}"

    def add_component(self, comp: component.Component):
        self.components.add(comp)
        if comp.is_public:
            self.publicComponents.add(comp)
        if isinstance(comp, Sensor):
            self.sensors.add(comp)

        if hasattr(comp, 'get_sensor_set'):
            sensor_set = comp.get_sensor_set()
            for i in sensor_set:
                self.sensors.add(i)

        # components using the same port use the same lock
        self._lock_dict = comp.update_lock(self._lock_dict)

    def add_component_list(self, component_list: list[component.Component]):
        for i in component_list:
            self.add_component(i)

    def save_all_data(self):
        for i in self.sensors:
            i.save_data()
