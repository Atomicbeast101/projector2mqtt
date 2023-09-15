# Imports
import bin.config
import datetime
import serial
import time

# Classes
class ProjectorException(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class Projector:
    def __init__(self, brand, model, port, log):
        self.projector_config = bin.config.SUPPORTED_PROJECTORS[brand.lower()][model.lower()]
        self.log = log

        self.power_on = False
        self.model = None
        self.last_turned_off = None

        # Connect to projector
        self.con = serial.Serial(
            port=port,
            baudrate=self.projector_config['baudrate'],
            parity=self.projector_config['parity'],
            stopbits=self.projector_config['stopbits'],
            bytesize=self.projector_config['bytesize'],
            timeout=bin.config.SERIAL_TIMEOUT,
            rtscts=False,
            dsrdtr=False
        )

        output = self._serial(self.projector_config['commands']['status'])
        if output == 'ON':
            self.power_on = True
        self.model = self._serial(self.projector_config['commands']['model'])

    def _read(self):
        output = ''
        while self.con.inWaiting() > 0:
            output += self.con.read(1).decode()
        return output

    def _serial(self, cmd):
        # Access console
        self.con.write(self.projector_config['handshake']['send'].encode())
        time.sleep(self.projector_config['handshake']['wait'])
        output = self._read()
        if output != self.projector_config['handshake']['expect']:
            raise ProjectorException('Unexpected serial output from the projector! Expecting {} but got {} instead (for {} command).'.format(self.projector_config['handshake']['expect'], output, cmd))

        # Send command
        self.log.debug('Command sent to serial device: {}'.format(cmd))
        self.con.write((cmd + self.projector_config['handshake']['send']).encode())
        time.sleep(self.projector_config['handshake']['wait'])
        output = self._read()
        self.log.debug('Output received from serial device: {}'.format(output.strip()))
        try:
            return output.strip()[1:-1].split('=')[1]
        except Exception:
            raise ProjectorException('Unexpected error when trying to process the returned output: {}!'.format(output))

    def updater(self):
        while True:
            output = self._serial(self.projector_config['commands']['status'])
            if output == 'ON':
                self.power_on = True
            elif output == 'OFF':
                self.power_on = False
            else:
                self.log.error('Unable to check power status of the projector! Output received: {}'.format(output))
            time.sleep(5)

    def status(self):
        # Get data from projector
        lamp_hours = self._serial(self.projector_config['commands']['lamp_hours']) # Unknown if it reports minutes or hours
        cooldown_left = -1
        if self.last_turned_off and datetime.datetime.now() > (self.last_turned_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)):
            cooldown_left = ((self.last_turned_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)) - datetime.datetime.now()).seconds / 60.0

        return {
            'model': self.model,
            'lamp_hours': lamp_hours,
            'power_on': self.power_on,
            'last_turned_off': self.last_turned_off,
            'cooldown_left': cooldown_left
        }

    def toggle(self):
        if self.power_on:
            return self.off()
        else:
            return self.on()

    def on(self):
        if self.last_turned_off and datetime.datetime.now() > (self.last_turned_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)):
            return False, {
                'reason': 'needs_cooldown',
                'data': ((self.last_turned_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)) - datetime.datetime.now()).seconds
            }

        status = self._serial(self.projector_config['commands']['on'])
        if status == 'ON':
            self.power_on = True
            return True, ''
        return False, {
            'reason': 'bad_data',
            'data': status
        }

    def off(self):
        status = self._serial(self.projector_config['commands']['off'])
        if status == 'OFF':
            self.last_turned_off = datetime.datetime.now()
            self.power_on = False
            return True, ''
        return False, {
            'reason': 'bad_data',
            'data': status
        }
