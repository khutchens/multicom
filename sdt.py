#!/usr/bin/env python3

import argparse
import glob
import re
import select
import serial
import socket
import yaml

class InputDeviceError(Exception): pass
class NoDeviceError(InputDeviceError): pass
class ConfigParseError(InputDeviceError): pass

class InputDevice:
    def __init__(self, name, config):
        self.name = name

        self.highlight = {}
        try:
            for pattern, sub in config['highlight'].items():
                self.highlight[re.compile(pattern)] = sub
        except KeyError:
            pass

    def __str__(self):
        return f'{self.name}: {self.label}'

    def _detect_type(self, config, key):
        try:
            setattr(self, key, config[key])
        except KeyError:
            raise NoDeviceError

    def _init_configs(self, config, keys):
        for key in keys:
            try:
                setattr(self, key, config[key])
            except KeyError:
                raise ConfigParseError(f'Missing config key: {key}')

    def read_line(self):
        line = self._read_line_raw()
        for pattern, sub in self.highlight.items():
            line = re.sub(pattern, sub, line)
        return f'{self.name}: {line}'

class SerialInputDevice(InputDevice):
    def __init__(self, name, config):
        super().__init__(name, config)
        self._detect_type(config, 'tty_path')
        self._init_configs(config, ['baud', 'parity', 'endline', 'timeout_s'])
        self.endline = self.endline.encode('utf-8').decode('unicode_escape').encode('utf-8')

        try:
            translate_parity = {
                'none': serial.PARITY_NONE,
                'even': serial.PARITY_EVEN,
                'odd':  serial.PARITY_ODD,
            }
            self.parity = translate_parity[self.parity]
        except KeyError:
            raise ConfigParseError("Invalid parity value: {}, expected one of: {}".format(self.parity, ', '.join(translate_parity.keys())))

        for pathglob in self.tty_path:
            paths = glob.glob(pathglob)
            if len(paths) == 0:
                continue
            elif len(paths) == 1:
                self.label = f'Serial TTY, {paths[0]}'
                try:
                    self.serial_device = serial.Serial(paths[0], self.baud, timeout=self.timeout_s, parity=self.parity)
                except serial.SerialException as e:
                    raise InputDeviceError(e)
                return
            else:
                raise ConfigParseError('Ambiguous path {} matches multiple devices: {}'.format(pathglob, ' '.join(paths)))

        raise InputDeviceError('No device found for: {}'.format(' '.join(self.tty_path)))

    def _read_line_raw(self):
        return self.serial_device.read_until(self.endline).rstrip(self.endline).decode('utf-8', errors='replace')

    def fileno(self):
        return self.serial_device.fileno()

class SocketInputDevice(InputDevice):
    def __init__(self, name, config):
        super().__init__(name, config)
        self._detect_type(config, 'tcp_port')
        raise NotImplementedError('TCP sockets not implemented yet')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config', nargs='+')
    args = parser.parse_args()

    config = {}

    # Read config file(s)
    for conf_fpath in args.config:
        try:
            with open(conf_fpath, 'r') as conf_file:
                print(f'Reading config file: {conf_fpath}')
                config.update(yaml.safe_load(conf_file))
        except FileNotFoundError as e:
            print(f'Failed opening {conf_fpath}: {e}')

    devices = []
    dev_confs = config

    # Initialize devices
    for dev_name in dev_confs:
        dev = None
        dev_conf = dev_confs[dev_name]

        for dev_type in [SerialInputDevice, SocketInputDevice]:
            try:
                dev = dev_type(dev_name, dev_conf)
            except NoDeviceError:
                pass
            except ConfigParseError as e:
                print(f'Failed parsing config for \'{dev_name}\': {e}')
            except InputDeviceError as e:
                print(f'Failed opening device \'{dev_name}\': {e}')

            if dev != None:
                break

        if dev != None:
            devices.append(dev)

    # Read input devices
    for d in devices:
        print(d)
    print("-----")
    try:
        while True:
            reads, writes, exes = select.select(devices, [], [])
            for r in reads:
                print(r.read_line())
    except KeyboardInterrupt:
        print("")
