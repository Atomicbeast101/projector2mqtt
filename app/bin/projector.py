# Imports
import bin.config
import threading
import datetime
import serial
import time

# Classes
class Projector:
    def __init__(self, brand, model, port, log):
        self._config = bin.config.SUPPORTED_PROJECTORS[brand.lower()][model.lower()]
        self._log = log
        self.lock = False

        self.running = 'off'
        self.model = None
        self.last_off = None
        self.lamp_hours = None
        self.cooldown_left = -1

        self._serial = serial.Serial(
            port=port,
            baudrate=self._config['baudrate'],
            parity=self._config['parity'],
            stopbits=self._config['stopbits'],
            bytesize=self._config['bytesize'],
            timeout=bin.config.SERIAL_TIMEOUT,
            rtscts=False,
            dsrdtr=False
        )

        output = self._execute(self._config['commands']['status'])
        if output == 'ON':
            self.running = 'on'
        self.model = self._execute(self._config['commands']['model'])

        # Start updater thread
        self._log.debug('Starting ProjectorUpdater thread...')
        threading.Thread(target=self.update, daemon=True, name='ProjectorUpdater').start()
        self._log.debug('Started ProjectorUpdater thread!')

    def _read(self):
        output = ''
        while self._serial.inWaiting() > 0:
            output += self._serial.read(1).decode()
        return output

    def _execute(self, cmd):
        # Access console
        self._serial.write(self._config['handshake']['send'].encode())
        time.sleep(self._config['handshake']['wait'])
        output = self._read()
        if output != self._config['handshake']['expect']:
            raise bin.exception.ProjectorException('Unexpected serial output from the projector! Expecting {} but got {} instead (for {} command).'.format(self._config['handshake']['expect'], output, cmd))

        # Execute command
        count = 0
        while True:
            self._serial.write((cmd + self._config['handshake']['send']).encode())
            self._log.debug('Command sent to serial device: {}'.format(cmd))
            time.sleep(self._config['handshake']['wait'])
            output = self._read()
            self._log.debug('Output received from serial device: {}'.format(output.strip()))
            if output == self._config['failed_response']:
                if count >= 1:
                    self._log.warning('Projector returned failed response "{}".'.format(output))
                    raise bin.exception.ProjectorException('Unexpected error when trying to process the returned output: {}!'.format(output))
                else:
                    self._log.warning('Projector returned failed response "{}". Trying again in 5 seconds.'.format(output))
                    time.sleep(1)
                    count += 1
            else:
                return output.strip()[1:-1].split('=')[1]

    def update(self):
        count = 0
        while True:
            while True:
                if not self.lock:
                    break
            
            self.lock = True
            self.cooldown_left = -1
            if self.last_off and datetime.datetime.now() > (self.last_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)):
                self.cooldown_left = ((self.last_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)) - datetime.datetime.now()).seconds / 60.0
            if count >= 3:
                self.lamp_hours = self._execute(self._config['commands']['lamp_hours'])
                count = 0
            output = self._execute(self._config['commands']['status'])
            self.lock = False
            if output == 'ON':
                self.running = 'on'
            elif output == 'OFF':
                self.running = 'off'
            else:
                self._log.error('Unable to check power status of the projector! Output received: {}'.format(output))
            count += 1
            time.sleep(5)

    def on(self):
        while True:
            if not self.lock:
                break

        if self.last_off and datetime.datetime.now() > (self.last_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)):
            return False, {
                'reason': 'needs_cooldown',
                'data': ((self.last_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)) - datetime.datetime.now()).seconds
            }

        self.lock = True
        status = self._execute(self._config['commands']['on'])
        self.lock = False
        if status == 'ON':
            self.running = 'on'
            return True, ''
        return False, {
            'reason': 'bad_data',
            'data': status
        }

    def off(self):
        while True:
            if not self.lock:
                break

        self.lock = True
        status = self._execute(self._config['commands']['off'])
        self.lock = False
        if status == 'OFF':
            self.last_off = datetime.datetime.now()
            self.running = 'off'
            return True, ''
        return False, {
            'reason': 'bad_data',
            'data': status
        }
