from ..components.stdlib import component
from queue import Queue


class Operation:
    def __init__(self, device: component.Component, cmd: str, wait: bool = False, description: str = None,
                 kwargs: dict = {}):

        assert isinstance(device, component.Component), "The input device must be an instance of Component or its " \
                                                        "subclass "
        assert isinstance(cmd, str), "The command must be a string"

        if not hasattr(device, cmd):
            raise ValueError(f'Device {device} does not have command {cmd}')

        self.device = device
        self.command = cmd
        self.wait = wait
        self.kwargs = kwargs
        self.is_done = False
        self.description = description

    def __repr__(self):
        return f"<{self.__class__.__name__}; device:{self.device}; command: {self.command}; description {self.description}>"

    def __str__(self):
        return f"<{self.__class__.__name__}; device:{self.device}; command: {self.command}; description {self.description}>"


class VirtualDevice(component.Component):
    def terminate(self):
        pass

    def __init__(self):
        super().__init__('Virtual Operation')

    def base_state(self):
        pass

    def open(self):
        pass

    def close(self):
        pass

    def sleep(self, seconds: float):
        ret = self._sleep(seconds)
        if self._force_terminated:
            self.log(f"Force terminated while doing {self.current_op}")
        return ret

    def force_terminate_operation(self):
        self._force_terminated = True


class VirtualOperation:
    def __init__(self, cmd: str, description: str = None, kwargs: dict = None):
        self.cmd = cmd
        self.kwargs = kwargs
        self.is_done = False
        self.description = description
        self.device = VirtualDevice()

    def wait_for_operation(self, op: Operation):
        self.device.current_op = f'Wait for operation {op.command} on {op.device}'
        while not op.is_done:
            self.device.sleep(0.01)
            # wait until completed
        self.device.current_op = None

    def delay(self, seconds: float):
        self.device.current_op = f"Delay {seconds} seconds"
        self.device.sleep(seconds)
        self.device.current_op = None

    @property
    def command(self):
        return self.cmd

    def __repr__(self):
        return f"<{self.__class__.__name__}; command:{self.cmd}; description: {self.description}>"

    def __str__(self):
        return f"<{self.__class__.__name__}; command: {self.cmd}; description: {self.description}>"


class PublicBlocker:
    def __init__(self):
        self.block_request: bool = True
        self.block_ready: bool = False
        self.taskQueue: Queue = Queue()
