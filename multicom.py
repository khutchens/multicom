#!/usr/bin/env python3

import argparse, re, select, serial, socket, yaml

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
        self.label = f'Serial TTY, {self.tty_path}'

        try:
            translate_parity = {
                'none': serial.PARITY_NONE,
                'even': serial.PARITY_EVEN,
                'odd':  serial.PARITY_ODD,
            }
            self.parity = translate_parity[self.parity]
        except KeyError:
            raise ConfigParseError("Invalid parity value: {}, expected one of: {}".format(self.parity, ', '.join(translate_parity.keys())))

        try:
            self.serial_device = serial.Serial(self.tty_path, self.baud, timeout=self.timeout_s, parity=self.parity)
        except serial.SerialException as e:
            raise InputDeviceError(e)
        except termios.error as e:
            raise InputDeviceError(e)

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
    parser.add_argument('-c', '--config', metavar='CONF_FILE', default='multicom.yaml')
    args = parser.parse_args()

    # Read config file
    try:
        with open(args.config, 'r') as conf_file:
            config = yaml.safe_load(conf_file)
    except IOError as e:
        error("Failed opening '{}': {}".format(args.config, str(e)))

    devices = []
    dev_confs = config['devices']

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

        if dev == None:
            print(f'Failed initializing \'{dev_name}\'')
        else:
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
