from .apparatus import Apparatus
from ..components.stdlib import component
from typing import Union
from .operation import Operation, VirtualOperation


class Protocol:
    """
    Instructions for a process.
    """

    def __init__(self, apparatus: Apparatus, name: str, description: str = None, block_public: bool = False):
        self.apparatus: Apparatus = apparatus
        self.name: str = name
        self.description = description
        self.component_list = []
        self.procedures: list[Union[Operation, VirtualOperation, Protocol]] = []
        self.progress = 0
        self.current_op = None
        self.current_description = None
        self.finished = False
        self.paused = False

        self.block_public = block_public
        self.public_set = set()

        # type checking
        if not isinstance(apparatus, Apparatus):
            raise TypeError(f"Must pass an Apparatus object. Got {type(apparatus)}, which is not an instance of "
                            f"Apparatus.")

    def __repr__(self):
        return f"<{self.__str__()}>"

    def __str__(self):
        return f"Protocol {self.name} defined over {repr(self.apparatus)}"

    def quick_add(self, device: component.Component, cmd: str, wait: bool = True, description: str = None,
                  kwargs: dict = {}):

        op = Operation(device, cmd, wait, description, kwargs)
        self.add_single_operation(op, description=description)
        return op

    def add_single_operation(self, op: Union[Operation, VirtualOperation], description: str = None):
        op.description = description

        # check if the device is in apparatus
        if (op.device not in self.apparatus.components) and (not isinstance(op, VirtualOperation)):
            raise ValueError(f'The device {op.device} must be in {self.apparatus}')

        self.procedures.append(op)
        if not isinstance(op, VirtualOperation):
            self.component_list.append(op.device)
            if op.device.is_public:
                self.public_set.add(op.device)
        else:
            self.apparatus.virtual_devices.add(op.device)
        return op

    def add_sub_protocol(self, sub_protocol):
        assert isinstance(sub_protocol, Protocol)
        self.procedures.append(sub_protocol)
        self.public_set = sub_protocol.public_set | self.public_set
        self.component_list += sub_protocol.component_list


    def add_operation(self, op: Union[list[Union[Operation, VirtualOperation]], Operation, VirtualOperation],
                      description: str = None):
        if isinstance(op, list):
            for i in op:
                if not (isinstance(i, Operation) or isinstance(i, VirtualOperation)):
                    raise TypeError(f"{op} must be an instance of Operation or VirtualOperation!")
            for i in op:
                i.description = description
                self.add_single_operation(i)
        elif isinstance(op, Operation) or isinstance(op, VirtualOperation):
            op.description = description
            self.add_single_operation(op)
        else:
            raise TypeError(f"{op} is not an instance of Operation or VirtualOperation")


