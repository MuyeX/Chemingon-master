import math
import threading
import time
import warnings
from queue import Queue
from threading import Thread
from typing import Union

import bqplot.figure
import bqplot.pyplot as plt
# import sys
import ipywidgets as widgets
import numpy as np
import pandas as pd
from IPython.display import display
from loguru import logger

from ..components.stdlib.component import Component
from ..components.stdlib.sensor import Sensor
from .apparatus import Apparatus
from .operation import Operation, VirtualOperation, PublicBlocker, VirtualDevice
from .protocol import Protocol
from .errors import ExperimentError, ErrorInfo, ErrorHandler


# from IPython import get_ipython


class Experiment:
    def __init__(self, apparatus: Apparatus, channels: int = 1, keep_running: bool = False, name: str = 'Experiment',
                 save_interval: int = 1, err_handler: ErrorHandler = ErrorHandler()):
        self.name = name
        self.thread_list: list[Thread] = []
        self.public_thread_list: list[Thread] = []
        self.sensor_thread_list: list[Thread] = []
        self.apparatus: Apparatus = apparatus
        self.channels: int = channels
        self.channel_queue: list[Queue] = []
        self._init_protocol: Union[Protocol, None] = None
        self._fini_protocol: Union[Protocol, None] = None
        self.keep_running = keep_running
        self.save_interval = save_interval
        self.base_state_all = False

        self.error_queue: Queue[ErrorInfo] = Queue()
        self.error_quit = False
        self.error_detail: Union[None, ErrorInfo] = None
        self.stop_all_upon_error = False
        self.err_handler: ErrorHandler = err_handler

        self.protocol_list = []
        self.is_running = False
        self.finished = False
        self.timer_start = None
        self.pause: bool = False
        self.pause_ready: int = 0
        self.live_protocol: set[Protocol] = set()

        self.directory = None

        for i in range(0, channels):
            self.channel_queue.append(Queue())
        # jobs in different channels are done in parallel, and jobs in the same channel are done sequentially

    @logger.catch()
    def _execute_operation(self, op: Operation, protocol: Protocol, dry_run: bool):
        try:
            if isinstance(op, Operation):
                if not hasattr(op.device, op.command):
                    op.is_done = True
                    raise AttributeError(f"Public device {op.device} does not have command {op.command}")
                attr = getattr(op.device, op.command)

                if not dry_run:
                    logger.info(f"Device {op.device} executing {op.command} with arguments {op.kwargs}; "
                                f"Description: {op.description}")
                    # execute the command
                    attr(**op.kwargs)
                else:
                    logger.info(
                        f"DRY RUN; Description: {op.description}; Device {op.device} execute {op.command}")
                    print(f"Description: {op.description}; Public device {op.device} execute {op.command}\n")

                op.is_done = True

            elif isinstance(op, VirtualOperation):
                if not hasattr(op, op.cmd):
                    op.is_done = True
                    raise AttributeError(f"Command {op.cmd} does not exist")
                # execute the command
                attr = getattr(op, op.cmd)
                attr(**op.kwargs)
                op.is_done = True

        except Exception as e:
            # self.error_queue.put((protocol, e))
            err = ErrorInfo(e, protocol, True, device=op.device)
            self.error_queue.put(err)
            raise e

    @logger.catch()
    def public_operator(self, device: Component, dry_run: bool = False):
        time.sleep(0.5)

        while not self.error_quit:
            time.sleep(0.1)
            if not device.taskQueue.empty():
                task, protocol = device.taskQueue.get(timeout=2)
                if isinstance(task, PublicBlocker):
                    blocker: PublicBlocker = task
                    blocker.block_ready = True
                    device.log(f'Occupied by protocol {protocol.name}')
                    while blocker.block_request and not self.error_quit:
                        device.current_op = f'Occupied by protocol {protocol.name}'
                        if not blocker.taskQueue.empty():
                            try:
                                task, protocol = blocker.taskQueue.get(timeout=2)
                                op: Union[Operation, VirtualOperation] = task
                                protocol: Protocol
                                if isinstance(op, Operation):
                                    assert op.device.is_public, f"Device {op.device} is not public"
                                self._execute_operation(op, protocol, dry_run)
                            except Exception as e:
                                err = ErrorInfo(e, protocol, device=device)
                                self.error_queue.put(err)
                        else:
                            time.sleep(0.1)
                        device.current_op = None
                else:
                    try:
                        op: Union[Operation, VirtualOperation] = task
                        protocol: Protocol
                        if isinstance(op, Operation):
                            assert op.device.is_public, f"Device {op.device} is not public"
                        self._execute_operation(op, protocol, dry_run)
                    except Exception as e:
                        err = ErrorInfo(e, protocol, device=device)
                        self.error_queue.put(err)
            else:
                if device.taskQueue.empty() and not self.keep_running:
                    count = 0
                    for i in self.thread_list:
                        if i.is_alive():
                            count += 1
                    if count == 0:
                        print(f"public device \"{device.name}\" shut down")
                        break
            self._pause_handler()

    def add_protocol(self, protocol: Protocol, channel: int = 1):
        assert 1 <= channel <= self.channels, f"Channel out of range. Only {self.channels} available"
        self.channel_queue[channel - 1].put(protocol)
        self.protocol_list.append(protocol)

    def initiation_protocol(self, protocol: Protocol):
        assert isinstance(protocol, Protocol)
        self._init_protocol = protocol

    def finishing_protocol(self, protocol: Protocol):
        assert isinstance(protocol, Protocol)
        self._fini_protocol = protocol

    @logger.catch()
    def _sensor_monitor(self, sensor: Sensor):
        while not sensor.stop:
            try:
                sensor.update()
                time.sleep(sensor.interval)
            except Exception as e:
                err = ErrorInfo(e, None, device=sensor)
                self.error_queue.put(err)
                time.sleep(int(1/sensor.freq) + 1)
            self._pause_handler()

    def start_sensor_thread(self, sensor: Sensor):
        sensor.save_start_time(self.timer_start, self.directory)
        tmp = Thread(target=self._sensor_monitor, args=(sensor, ))
        self.sensor_thread_list.append(tmp)
        tmp.start()

    @logger.catch()
    def _open_all_components(self):
        for device in self.apparatus.components:
            device.open()

        for sensor in self.apparatus.sensors:
            self.start_sensor_thread(sensor)

    def _close_all_components(self):
        for sensor in self.apparatus.sensors:
            try:
                sensor.terminate()
            except Exception as e:
                warnings.warn(f'Error when terminating sensor {sensor.name}: {e}')

        if self.base_state_all:
            for device in self.apparatus.components:
                try:
                    device.base_state()
                except Exception as e:
                    warnings.warn(f'Error when setting device {device.name} to base state: {e}')

        for device in self.apparatus.components:
            try:
                device.close()
            except Exception as e:
                warnings.warn(f'Error when closing device {device.name}: {e}')

    @staticmethod
    def time_difference(time_start: float, time_end: float):
        timedelta = int(time_end - time_start)
        time_sec = timedelta % 60
        timedelta = math.floor(timedelta / 60)
        time_min = timedelta % 60
        timedelta = math.floor(timedelta / 60)
        time_hrs = timedelta
        return '{:0>2d}:{:0>2d}:{:0>2d}'.format(time_hrs, time_min, time_sec)
        # return f'{time_hrs} : {time_min} : {time_sec}'

    @logger.catch()
    def master_operator(self, channel: int, dry_run: bool = False):
        if self.keep_running:
            while True:
                protocol = self.channel_queue[channel - 1].get()
                self._execute_protocol(protocol, dry_run=dry_run)

        else:
            while not self.channel_queue[channel - 1].empty():
                protocol = self.channel_queue[channel - 1].get()
                self._execute_protocol(protocol, dry_run=dry_run)

    @logger.catch()
    def force_stop_all(self, e: Exception):
        self.error_quit = True
        for i in self.apparatus.components:
            try:
                i.force_terminate_operation()
            except Exception as err:
                warnings.warn(f'Error when terminating device {i.name}: {err}')
        for i in self.apparatus.virtual_devices:
            i: VirtualDevice
            try:
                i.force_terminate_operation()
            except Exception as err:
                warnings.warn(f'Error when terminating virtual device {i}: {err}')
        time.sleep(1)
        logger.debug(f"Force stop all: {e}")
        print(f"Force stop all: {e}")

    def start_master_operators(self, dry_run: bool = False):
        self.is_running = True
        self.timer_start = time.time()
        time_str = time.strftime('%d%h%y_%H%M%S', time.localtime(self.timer_start))
        self.directory = f'experiment_results/{self.name}_{time_str}'

        logger.add(f'{self.directory}/{self.name}_' + '{time}.log')
        logger.info(f'Experiment started with dry run = {dry_run}')

        if not dry_run:
            self._open_all_components()

        time.sleep(0.5)

        start_threading_no = threading.active_count()
        public_list = self.apparatus.publicComponents
        self.public_thread_list: list[Thread] = []
        for i in public_list:
            tmp = Thread(target=self.public_operator, args=(i, dry_run,))
            tmp.setDaemon(True)
            tmp.start()
            self.public_thread_list.append(tmp)

        if self._init_protocol is not None:
            self._execute_protocol(self._init_protocol, dry_run=dry_run)

        self.thread_list: list[Thread] = []
        for i in range(0, self.channels):
            tmp = Thread(target=self.master_operator, args=(i, dry_run,))
            tmp.setDaemon(True)
            tmp.start()
            self.thread_list.append(tmp)

        time_count = 0
        while True:
            sleep_time = 0.001
            time_count_target = int(1 / sleep_time)
            time.sleep(sleep_time)
            time_count += 1
            if time_count == time_count_target:
                time_count = 0
                self.apparatus.save_all_data()

            if not self.error_queue.empty():
                # error raised in some thread
                #  (protocol, e) = self.error_queue.get()
                #  self.error_detail = (protocol, e)

                err: ErrorInfo = self.error_queue.get()
                self.error_detail: ErrorInfo = err
                e = err.error

                print(f"Error raised: {e}")
                logger.error(f'Error raised: {e}')

                if not self.stop_all_upon_error:
                    if err.fatality:
                        logger.info(f'Fatal error; Quitting...')
                        self.force_stop_all(e)
                    else:
                        self.pause = True
                        logger.info(f'Pausing')
                        solution_protocol: Protocol = self.err_handler.get_solution(self.error_detail)
                        all_ready = False
                        while not all_ready:
                            time.sleep(0.1)
                            all_ready = True
                            for i in self.live_protocol:
                                if not i.paused:
                                    all_ready = False
                        logger.debug(f'Paused')
                        self._execute_error_protocol(solution_protocol, dry_run)
                        if not self.error_detail.pause:
                            logger.info(f'Resumed')
                            self.pause = False
                        self.error_detail = None

                else:
                    self.force_stop_all(e)

            if threading.active_count() <= start_threading_no:
                break

        if (not self.error_quit) and (self._fini_protocol is not None):
            self._execute_protocol(self._fini_protocol, dry_run=dry_run)

        for i in self.thread_list:
            i.join()

        if self.error_quit:
            self.error_quit = False
            self._execute_error_protocol(self.err_handler.get_solution(self.error_detail), dry_run=dry_run)
            self.error_quit = True

        for i in self.public_thread_list:
            i.join()

        if not dry_run:
            logger.info('Closing all devices')
            print('close all devices')
            self._close_all_components()

        for i in self.sensor_thread_list:
            i.join()

        self.is_running = False
        self.finished = True
        logger.info("End of experiment")
        print("End of experiment")

    def _pause_handler(self, target=None):
        if self.pause:
            self.pause_ready += 1
            if isinstance(target, Protocol):
                target.paused = True

            while self.pause:
                time.sleep(0.1)

            if isinstance(target, Protocol):
                target.paused = False
            self.pause_ready -= 1

    @logger.catch()
    def _execute_error_protocol(self, protocol: Union[Protocol, None], dry_run: bool = False):
        if protocol is None:
            return

        try:
            logger.info(f'Error protocol {protocol.name}: started')
            print(f'Error protocol {protocol.name}: started')
            for task in protocol.procedures:
                protocol.progress+=1
                if isinstance(task, Protocol):
                    protocol.current_op = f'sub protocol: {task.name}'
                    protocol.current_description = task.description
                    logger.info(f'Error protocol {protocol.name} executing sub protocol: {task.name}')
                    self._execute_error_protocol(task, dry_run=dry_run)
                    protocol.current_op = None
                    protocol.current_description = protocol.description
                else:
                    op: Operation = task
                    protocol.current_op = f'{op.device.name}: {op.command}'
                    protocol.current_description = op.description
                    logger.info(f'Error protocol {protocol.name}: executing {op.command} on {op.device.name}')
                    self._execute_operation(op, protocol, dry_run)
                    if self.error_quit:
                        break
                    protocol.current_op = None
        except Exception as e:
            logger.error(f'Error when executing error protocol {protocol}: {e}')
            err = ErrorInfo(e, protocol, fatality=True)
            self.error_queue.put(err)
            protocol.current_description = 'Error'
        protocol.finished = True
        logger.info(f'Error protocol {protocol.name}: finished')
        print(f'Error protocol {protocol.name}: finished')

    @logger.catch()
    def _execute_protocol(self, protocol: Union[Protocol, None], dry_run: bool = False):
        if protocol is None:
            return
        self.live_protocol.add(protocol)
        try:
            logger.info(f'Protocol {protocol.name}: started')
            if protocol.block_public:
                logger.info(f'Protocol {protocol.name}: blocking public components')
                blocker_dict = {}
                for device in protocol.public_set:
                    device: Component
                    tmp_blocker = PublicBlocker()
                    device.taskQueue.put((tmp_blocker, protocol))
                    blocker_dict[device] = tmp_blocker

                not_ready = True
                while not_ready and not self.error_quit:
                    not_ready = False
                    for i in blocker_dict:
                        if not blocker_dict[i].block_ready:
                            not_ready = True
                    time.sleep(0.1)
                    self._pause_handler(protocol)
                self._pause_handler(protocol)

                logger.info(f'Protocol {protocol.name}: public components ready')

            for task in protocol.procedures:
                protocol.progress += 1

                try:
                    if isinstance(task, Protocol):
                        protocol.current_op = f'sub protocol: {task.name}'
                        protocol.current_description = task.description
                        logger.info(f'protocol {protocol.name} executing sub protocol: {task.name}')
                        self.live_protocol.remove(protocol)
                        self._execute_protocol(task, dry_run=dry_run)
                        self.live_protocol.add(protocol)
                        protocol.current_op = None
                        protocol.current_description = protocol.description
                    else:
                        op: Operation = task
                        protocol.current_op = f'{op.device.name}: {op.command}'
                        protocol.current_description = op.description
                        logger.info(f'Protocol {protocol.name}: executing {op.command} on {op.device.name}')
                        if op.device.is_public:
                            if not protocol.block_public:
                                q = op.device.taskQueue
                            else:
                                q = blocker_dict[op.device].taskQueue
                            q.put((op, protocol))
                            if op.wait:
                                while not op.is_done and not self.error_quit:
                                    time.sleep(0.01)
                                    self._pause_handler(protocol)
                                    # wait until completed
                        else:
                            self._execute_operation(op, protocol, dry_run)
                        if self.error_quit:
                            break
                        protocol.current_op = None
                except ExperimentError as e:
                    err = ErrorInfo(e, protocol, device=task.device if isinstance(task, Operation) else None)
                    self.error_queue.put(err)
                    protocol.current_description = 'Error'

                self._pause_handler(protocol)

            if not self.error_quit:
                protocol.finished = True
            else:
                protocol.current_description = 'Stopped'

            if protocol.block_public:
                for device in protocol.public_set:
                    blocker_dict[device].block_request = False

        except Exception as e:
            # self.error_queue.put((protocol, e))
            err = ErrorInfo(e, protocol, True)
            self.error_queue.put(err)
            protocol.current_description = 'Error'
            # raise e
        self.live_protocol.remove(protocol)
        logger.info(f'Protocol {protocol.name}: finished')

    def start_jupyter_ui(self):
        ui = JupyterUI(self)
        ui.start_jupyter_ui()


class JupyterUI:
    def __init__(self, exp: Experiment):
        self.device_dict = None
        self.devices_ui = None
        self.channel_dict = None
        self.exp_info_ui = None
        self.exp_dict = None
        self.exp_control_ui = None
        self.exp = exp
        self.sensor_panel = None
        self.sensors_dict = None

    def draw_exp_control(self):
        def do_start_btn(btn):
            if exp_dry_run.value:
                exp_stop_all.value = True
            self.exp.stop_all_upon_error = exp_stop_all.value
            force_stop_btn.disabled = False
            exp_status_label.description = 'Running'
            btn.description = 'Running'
            btn.disabled = True
            btn.tooltip = 'Running'
            btn.icon = 'hourglass'
            thread = Thread(target=self.exp.start_master_operators, args=(exp_dry_run.value,))
            thread.start()

        def do_stop_btn(btn):
            exp_status_label.description = 'Stopped'
            exp_status_label.value = False
            self.exp.stop_all_upon_error = exp_stop_all.value
            err = ErrorInfo(ExperimentError('Force stop button'), None, True)
            self.exp.error_queue.put(err)
            # self.exp.error_queue.put((None, KeyboardInterrupt('Force stopped')))

        def do_pause_btn(btn):
            logger.debug('Pause button pressed')
            if not self.exp.pause:
                self.exp.pause = True

        def do_resume_btn(btn):
            logger.debug('Resume button pressed')
            if self.exp.error_detail is None:
                self.exp.pause = False

        start_btn = widgets.Button(
            description='Start',
            disabled=False,
            button_style='',  # 'success', 'info', 'warning', 'danger' or ''
            tooltip='Start',
            icon='play'  # (FontAwesome names without the `fa-` prefix)
        )
        start_btn.on_click(do_start_btn)

        force_stop_btn = widgets.Button(
            description='Force Stop',
            disabled=True,
            button_style='danger',  # 'success', 'info', 'warning', 'danger' or ''
            tooltip='Force Stop',
            icon='stop'  # (FontAwesome names without the `fa-` prefix)
        )
        force_stop_btn.on_click(do_stop_btn)

        pause_btn = widgets.Button(
            description='Pause',
            disabled=True,
            button_style='',
            tooltip='Pause',
            icon='pause-circle'
        )
        pause_btn.on_click(do_pause_btn)

        resume_btn = widgets.Button(
            description='Resume',
            disabled=True,
            button_style='',
            tooltip='Resume',
            icon='play-circle'
        )
        resume_btn.on_click(do_resume_btn)

        # exp_status_label = widgets.Label(value="Status")
        exp_status_label = widgets.Valid(
            value=True,
            description='Ready',
        )

        run_time_label = widgets.Label(value="00:00:00")

        exp_control_main = widgets.HBox([start_btn, force_stop_btn, pause_btn, resume_btn, exp_status_label, run_time_label],
                                        layout=widgets.Layout(flex_flow='row', display='flex', width='100%',
                                                              justify_content='space-between'))
        exp_control_title = widgets.HTML(
            value="<h4><b>Experiment Control</b></h4>",
        )

        exp_dry_run = widgets.Checkbox(value=False, description='Dry run', indent=False,
                                       layout=widgets.Layout(width='70px'))
        exp_stop_all = widgets.Checkbox(value=False, description='Stop all upon error', indent=True,
                                        layout=widgets.Layout(width='250px'))
        exp_settings = widgets.HBox([exp_dry_run, exp_stop_all], layout=widgets.Layout(justify_content='flex-start'))
        # exp_settings = widgets.HBox([exp_dry_run], layout=widgets.Layout(justify_content='flex-start'))

        exp_control = widgets.VBox([exp_control_title, exp_control_main, exp_settings])
        exp_dict = dict()  # update with this
        exp_dict['start_btn'] = start_btn
        exp_dict['force_stop'] = force_stop_btn
        exp_dict['status'] = exp_status_label
        exp_dict['run_time'] = run_time_label
        exp_dict['dry_run'] = exp_dry_run
        exp_dict['stop_all'] = exp_stop_all
        exp_dict['pause_btn'] = pause_btn
        exp_dict['resume_btn'] = resume_btn

        self.exp_dict = exp_dict
        self.exp_control_ui = exp_control

    def draw_exp_info(self):
        # Experiment info
        exp_info_title = widgets.HTML(
            value="<h4><b>Experiment Information</b></h4>",
        )
        channel_HBox_list = []
        channel_dict = dict()  # update ui with this
        for i in range(0, len(self.exp.protocol_list)):
            protocol = self.exp.protocol_list[i]
            channel_label = widgets.Label(value=protocol.name, layout=widgets.Layout(flex='0 0 auto'))
            pg_bar = widgets.widgets.IntProgress(
                value=0,
                min=0,
                max=len(protocol.procedures),
                description='Ready',
                bar_style='',  # 'success', 'info', 'warning', 'danger' or ''
                # style={'bar_color': 'cyan'},
                orientation='horizontal'
            )
            channel_description_box = widgets.Text(
                value=protocol.description,
                placeholder='No description',
                description='Description:',
                disabled=True
            )
            current_op = widgets.Text(
                value='Inactive',
                placeholder='Inactive',
                description='Operation',
                disabled=True,
                layout={'overflow': 'scroll'}
            )
            channel_hb = widgets.HBox([channel_label, pg_bar, channel_description_box, current_op],
                                      layout=widgets.Layout(flex_flow='row', display='flex', width='auto',
                                                            justify_content='flex-start'))
            channel_HBox_list.append(channel_hb)

            single_channel_dict = dict()
            single_channel_dict['label'] = channel_label
            single_channel_dict['pg_bar'] = pg_bar
            single_channel_dict['description'] = channel_description_box
            single_channel_dict['op'] = current_op

            channel_dict[protocol] = single_channel_dict

        exp_info = widgets.VBox([exp_info_title] + channel_HBox_list)
        self.exp_info_ui = exp_info
        self.channel_dict = channel_dict

    @staticmethod
    def draw_single_device_mon(device: Component, operation=''):
        name = device.name
        port = device.get_port
        connected = device.is_connected
        description = device.description

        device_name = widgets.Label(value=name, layout=widgets.Layout(height='auto', width='auto'))
        device_port = widgets.Text(value=port, placeholder='Undefined', description='Port', disabled=True)
        device_connected = widgets.Valid(
            value=connected,
            description='Disconnected',
        )
        device_description = widgets.Textarea(value=description, placeholder='None', disabled=True,
                                              layout=widgets.Layout(height='30px', width='auto'))
        device_operation = widgets.Text(value=operation, placeholder='Inactive', disabled=True,
                                        layout=widgets.Layout(height='auto', width='auto'))
        device_button_connect = widgets.Button(description='Wait', disabled=False, button_style='',
                                               tooltip='Connect', icon='connect',
                                               layout=widgets.Layout(width='auto'))
        device_button_connect.on_click(device.btn_change_connection)
        device_grid = widgets.GridspecLayout(2, 4, height='80px')

        device_grid[:, 0] = device_name
        device_grid[0, 1] = device_port
        device_grid[0, 2] = device_connected
        device_grid[0, 3] = device_button_connect
        device_grid[1, 1:2] = device_description
        device_grid[1, 2:4] = device_operation

        tmp_single_device_dict = dict()
        tmp_single_device_dict['name'] = device_name
        tmp_single_device_dict['port'] = device_port
        tmp_single_device_dict['connected'] = device_connected
        tmp_single_device_dict['button_connect'] = device_button_connect
        tmp_single_device_dict['description'] = device_description
        tmp_single_device_dict['operation'] = device_operation

        return device_grid, tmp_single_device_dict

    def draw_device_ui(self):
        instruments_info_title = widgets.HTML(
            value="<h4><b>Instruments Information</b></h4>",
        )

        accordion_list = [None]
        public_instrument_list = []
        device_dict = dict()  # update ui with this
        for protocol_i in self.exp.protocol_list:
            instrument_list = []
            for protocol_device in set(protocol_i.component_list):
                if protocol_device not in device_dict:
                    ui, single_device_dict = self.draw_single_device_mon(protocol_device)
                    device_dict[protocol_device] = single_device_dict

                    if protocol_device.is_public:
                        public_instrument_list.append(ui)
                    else:
                        instrument_list.append(ui)
            instrument_vbox = widgets.VBox(instrument_list)
            accordion_list.append(instrument_vbox)
        accordion_list[0] = widgets.VBox(public_instrument_list)
        instrument_accordion = widgets.Accordion(accordion_list)
        instrument_accordion.set_title(0, 'Public Devices')
        for i in range(0, len(self.exp.protocol_list)):
            instrument_accordion.set_title(i + 1, self.exp.protocol_list[i].name)

        self.devices_ui = widgets.VBox([instruments_info_title, instrument_accordion])
        self.device_dict = device_dict

    def update_exp(self):
        tmp_exp_dict = self.exp_dict

        tmp_start_btn: widgets.Button = tmp_exp_dict['start_btn']
        tmp_force_stop_btn: widgets.Button = tmp_exp_dict['force_stop']
        tmp_exp_status_label: widgets.Valid = tmp_exp_dict['status']
        tmp_run_time_label: widgets.Label = tmp_exp_dict['run_time']
        tmp_exp_dry_run: widgets.Checkbox = tmp_exp_dict['dry_run']
        tmp_exp_stop_all: widgets.Checkbox = tmp_exp_dict['stop_all']
        tmp_pause_btn: widgets.Button = tmp_exp_dict['pause_btn']
        tmp_resume_btn: widgets.Button = tmp_exp_dict['resume_btn']

        if not self.exp.error_quit:
            if self.exp.finished is False and self.exp.is_running is False:
                tmp_exp_status_label.description = 'Ready'
                tmp_exp_status_label.value = True
                tmp_start_btn.disabled = False
                tmp_force_stop_btn.disabled = True
                tmp_pause_btn.disabled = tmp_resume_btn.disabled = True
                tmp_resume_btn.button_style = ''
            elif self.exp.finished is False and self.exp.is_running is True:
                if not self.exp.pause:
                    tmp_exp_status_label.description = 'Running'
                tmp_exp_status_label.value = True
                tmp_start_btn.disabled = True
                tmp_force_stop_btn.disabled = False
                if self.exp.pause:
                    if self.exp.error_detail is None:
                        tmp_exp_status_label.description = 'Paused'
                    else:
                        tmp_exp_status_label.description = 'Exception'
                    tmp_pause_btn.disabled = True
                    if self.exp.error_detail is None:
                        tmp_resume_btn.disabled = False
                        tmp_resume_btn.button_style = 'success'
                    else:
                        tmp_resume_btn.disabled = True
                else:
                    tmp_pause_btn.disabled = False
                    tmp_resume_btn.disabled = True
                    tmp_resume_btn.button_style = ''

            elif self.exp.finished is True and self.exp.is_running is False:
                tmp_exp_status_label.description = 'Finished'
                tmp_exp_status_label.value = True
                tmp_start_btn.disabled = True
                tmp_start_btn.button_style = 'success'
                tmp_start_btn.tooltip = 'Finished'
                tmp_start_btn.description = 'Finished'
                tmp_start_btn.icon = 'check'
                tmp_force_stop_btn.disabled = True
                tmp_resume_btn.disabled = tmp_pause_btn.disabled = True
                tmp_resume_btn.button_style = ''
            elif self.exp.finished:
                tmp_start_btn.disabled = True
                tmp_force_stop_btn.disabled = True
                tmp_resume_btn.disabled = tmp_pause_btn.disabled = True
                tmp_resume_btn.button_style = ''
        else:
            tmp_resume_btn.disabled = tmp_pause_btn.disabled = True
            if self.exp.is_running is False:
                tmp_exp_status_label.description = 'Error'
                tmp_exp_status_label.value = False
                tmp_start_btn.disabled = True
                tmp_force_stop_btn.disabled = True
            else:
                tmp_exp_status_label.description = 'Stopping'
                tmp_exp_status_label.value = False
                tmp_start_btn.disabled = True
                tmp_force_stop_btn.disabled = True

        if self.exp.is_running:
            tmp_run_time_label.value = self.exp.time_difference(self.exp.timer_start, time.time())  # todo runtime

    def update_channel(self):
        tmp_channel_dict = self.channel_dict
        error_protocol = None
        if self.exp.error_detail is not None:
            error_protocol = self.exp.error_detail.protocol
            e = self.exp.error_detail.error

        for tmp_protocol in self.channel_dict:
            if tmp_protocol == error_protocol:
                tmp_protocol: Protocol
                tmp_single_channel_dict = tmp_channel_dict[error_protocol]
                tmp_pg_bar: widgets.IntProgress = tmp_single_channel_dict['pg_bar']
                tmp_channel_description_box: widgets.Text = tmp_single_channel_dict['description']
                tmp_current_op: widgets.Text = tmp_single_channel_dict['op']

                tmp_pg_bar.value = tmp_protocol.progress
                tmp_pg_bar.bar_style = 'danger'
                tmp_channel_description_box.value = 'Error'
                if tmp_protocol.current_op is not None:
                    tmp_current_op.value = tmp_protocol.current_op

            else:
                tmp_protocol: Protocol
                tmp_single_channel_dict = tmp_channel_dict[tmp_protocol]
                tmp_pg_bar: widgets.IntProgress = tmp_single_channel_dict['pg_bar']
                tmp_channel_description_box: widgets.Text = tmp_single_channel_dict['description']
                tmp_current_op: widgets.Text = tmp_single_channel_dict['op']

                tmp_pg_bar.value = tmp_protocol.progress
                if tmp_protocol.current_op is not None:
                    tmp_current_op.value = tmp_protocol.current_op
                else:
                    tmp_current_op.value = ''

                if tmp_protocol.finished:
                    tmp_pg_bar.bar_style = 'success'
                    tmp_channel_description_box.value = 'Finished'
                else:
                    if tmp_protocol.current_description is not None:
                        tmp_channel_description_box.value = tmp_protocol.current_description

    def update_devices(self):
        tmp_device_dict = self.device_dict

        for single_device in tmp_device_dict:
            single_device: Component
            tmp_single_device_dict = tmp_device_dict[single_device]
            # tmp_device_name = tmp_single_device_dict['name']
            tmp_device_port: widgets.Text = tmp_single_device_dict['port']
            tmp_device_connected: widgets.Valid = tmp_single_device_dict['connected']
            tmp_device_button_connect: widgets.Button = tmp_single_device_dict['button_connect']
            tmp_device_description: widgets.Textarea = tmp_single_device_dict['description']
            tmp_device_operation: widgets.Text = tmp_single_device_dict['operation']

            tmp_device_port.value = single_device.get_port
            tmp_device_connected.value = single_device.is_connected
            tmp_device_connected.description = 'Connected' if single_device.is_connected else 'Disconnected'
            if single_device.is_connected:
                if not tmp_device_button_connect.description == 'Disconnect':
                    time.sleep(0.2)
                    tmp_device_button_connect.description = 'Disconnect'
                    tmp_device_button_connect.button_style = 'Danger'
                    tmp_device_button_connect.icon = 'cross'
            else:
                if not tmp_device_button_connect.description == 'Connect':
                    time.sleep(0.2)
                    tmp_device_button_connect.description = 'Connect'
                    tmp_device_button_connect.button_style = ''
                    tmp_device_button_connect.icon = 'check'
            tmp_device_description.value = '' if single_device.description_display is None else single_device.description_display
            tmp_device_operation.value = '' if single_device.current_op is None else single_device.current_op

    def update_sensors(self):
        for sensor in self.sensors_dict:
            for channel in self.sensors_dict[sensor]:
                line: bqplot.marks.Scatter = self.sensors_dict[sensor][channel][1]
                data: pd.DataFrame = sensor.data
                xdata = np.array(data['time'])
                ydata = np.array(data[channel])

                tmp = 60*sensor.freq
                if len(xdata) >= tmp:
                    line.x = xdata[-tmp:]
                    line.y = ydata[-tmp:]
                else:
                    line.x = xdata
                    line.y = ydata

    def update_ui(self):
        while True:
            time.sleep(0.1)
            self.update_exp()
            self.update_channel()
            self.update_devices()
            self.update_sensors()

            if self.exp.finished:
                self.update_exp()
                self.update_channel()
                self.update_devices()
                self.update_sensors()
                break

    @staticmethod
    def draw_single_sensor(sensor: Sensor):
        # print(f"drawing sensor {sensor}")
        plot_dict: dict[bqplot.figure.Figure] = dict()
        for channel in sensor.channels:
            data: pd.DataFrame = sensor.data
            xdata = np.array(data['time'])
            ydata = np.array(data[channel])

            def_tt = bqplot.Tooltip(
                fields=["x", "y"], formats=[".2f", ".2f"], labels=["Time(s)", channel]
            )
            fig = plt.figure(title=f"{sensor.name}: {channel}",
                             fig_margin={'top': 50, 'bottom': 30, 'left': 50, 'right': 30})
            fig.layout.height = '300px'
            fig.layout.width = '300px'
            scatter = plt.plot(x=xdata, y=ydata, default_size=5, tooltip=def_tt)
            plt.xlabel('Time(s)')
            plt.ylabel(channel)

            plot_dict[channel] = (fig, scatter)

        return plot_dict

    def draw_sensors(self):
        # print('draw all sensors')
        self.sensors_dict = dict()
        plot_list = []
        for sensor in self.exp.apparatus.sensors:
            self.sensors_dict[sensor] = self.draw_single_sensor(sensor)
            for key in self.sensors_dict[sensor]:
                plot_list.append(self.sensors_dict[sensor][key][0])

        sensors_title = widgets.HTML(value="<h4><b>Sensors</b></h4>", )
        vbox_list = [sensors_title]
        hbox_list = []
        for plot in plot_list:
            if len(hbox_list) == 3:
                vbox_list.append(widgets.HBox(hbox_list, layout=widgets.Layout(width='auto', height='310px')))
                hbox_list = []
            hbox_list.append(plot)
        if len(hbox_list) > 0:
            vbox_list.append(widgets.HBox(hbox_list, layout=widgets.Layout(width='auto', height='310px')))

        self.sensor_panel = widgets.VBox(vbox_list)

    def start_jupyter_ui(self):
        self.draw_exp_control()
        self.draw_exp_info()
        self.draw_device_ui()
        self.draw_sensors()

        display(self.exp_control_ui)
        display(self.exp_info_ui)
        display(self.sensor_panel)
        display(self.devices_ui)

        tmp_ui_thread = Thread(target=self.update_ui, args=())
        tmp_ui_thread.setDaemon(True)

        tmp_ui_thread.start()
        if self.exp.finished:
            tmp_ui_thread.join()
