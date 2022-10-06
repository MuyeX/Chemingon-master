from .combinedComponent import CombinedComponent
from .dummyComponent import DummyComponent
from .dummySensor import DummySensor


class DummyCombinedDevice(CombinedComponent):
    def __init__(self, name: str, is_public: bool = False, description: str = None, keep_log=True):
        super().__init__(name, is_public, description, keep_log)
        self.dum1 = DummyComponent('combined dum 1')
        self.dum2 = DummyComponent('combined dum 2')
        self.sen1 = DummySensor('combined dumSen 1', freq=1)

        self._add_components([self.dum1, self.dum2, self.sen1])

    def do_something(self):
        self.dum1.do_something('combined dum 1 doing')
        self._sleep(2)
        self.dum2.do_something('combined dum 2 doing')
