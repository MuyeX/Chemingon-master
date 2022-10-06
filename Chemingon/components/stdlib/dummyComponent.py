from .component import Component
import time
import random


class DummyComponent(Component):
    def do_something(self, output: str = "nothing"):

        if self.is_connected:
            for i in range(0, 2):
                if self._force_terminated:
                    break
                self.current_op = f'do_something: now at {i}'
                self._sleep(random.uniform(1.0, 3.0))
                # print(f"device {self.name} is doing something {i}: {output}\n")
                self.log(f"doing {output}: i = {i}")

            self.current_op = 'Inactive'
        else:
            raise RuntimeError(f'{self.name} not connected')

        # print(f"device {self.name} done!")
        self.log(f"device {self.name} done!")

    def base_state(self):
        self.log(f"device {self.name} is set to base_state")

    def open(self):
        # print(f'{self.name} connected')
        self.log(f'{self.name} connected')
        self.is_connected = True

    def close(self):
        self.log(f'{self.name} disconnected')
        # print(f'{self.name} disconnected')
        self.is_connected = False

    def terminate(self):
        pass
