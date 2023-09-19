# Imports
import bin.exception
import threading
import serial
import time

# Classes
class Communicator:
    def __init__(self, config, port, log):
        self._lock = threading.Lock()

        self._config = config
        self._log = log

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
    
    def _read(self):
        output = ''
        while self._serial.inWaiting() > 0:
            output += self._serial.read(1).decode()
        return output

    def execute(self, cmd):
        self._lock.acquire()

        # Access console
        self._serial.write(self._config['handshake']['send'].encode())
        time.sleep(self._config['handshake']['wait'])
        output = self._read()
        if output != self._config['handshake']['expect']:
            raise bin.exception.ProjectorException('Unexpected serial output from the projector! Expecting {} but got {} instead (for {} command).'.format(self._config['handshake']['expect'], output, cmd))

        # Send command & receive output
        while True:
            self._log.debug('Command sent to serial device: {}'.format(cmd))
            self._serial.write((cmd + self._config['handshake']['send']).encode())
            time.sleep(self._config['handshake']['wait'])
            output = self._read()
            self._log.debug('Output received from serial device: {}'.format(output.strip()))
            try:
                return output.strip()
            except Exception:
                raise bin.exception.ProjectorException('Unexpected error when trying to process the returned output: {}!'.format(output))
            finally:
                self._lock.release()
