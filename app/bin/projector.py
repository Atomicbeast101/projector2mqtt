# Imports
import bin.communicator
import bin.config
import datetime
import time

# Classes

class Projector:
    def __init__(self, brand, model, port, log):
        self._config = bin.config.SUPPORTED_PROJECTORS[brand.lower()][model.lower()]
        self.log = log

        self.running = 'off'
        self.model = None
        self.last_off = None
        
        self.lamp_hours = None

        self._con = bin.communicator.Communicator(self._config, port, log)

        output = self._execute(self._config['commands']['model'])
        if output == 'ON':
            self.running = 'on'
        self.model = self._execute(self._config['commands']['model'])

    def _execute(self, cmd):
        count = 0
        while True:
            output = self._con.execute(cmd)
            if output == self._config['failed_response']:
                if count >= 1:
                    self._log.warning('Projector returned failed response "{}".'.format(output))
                    raise bin.exception.ProjectorException('Unexpected error when trying to process the returned output: {}!'.format(output))
                else:
                    self._log.warning('Projector returned failed response "{}". Trying again in 5 seconds.'.format(output))
                    time.sleep(5)
                    count += 1
            else:
                return output.strip()[1:-1].split('=')[1]

    def updater(self):
        count = 0
        while True:
            if count >= 3:
                self.lamp_hours = self._execute(self._config['commands']['lamp_hours'])
                count = 0
            output = self._execute(self._config['commands']['status'])
            if output == 'ON':
                self.running = 'on'
            elif output == 'OFF':
                self.running = 'off'
            else:
                self.log.error('Unable to check power status of the projector! Output received: {}'.format(output))
            count += 1
            time.sleep(5)

    def metrics(self):
        cooldown_left = -1
        if self.last_off and datetime.datetime.now() > (self.last_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)):
            cooldown_left = ((self.last_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)) - datetime.datetime.now()).seconds / 60.0

        return {
            'model': self.model,
            'lamp_hours': self.lamp_hours,
            'running': self.running,
            'last_off': self.last_off,
            'cooldown_left': cooldown_left
        }

    def toggle(self):
        if self.running == 'on':
            return self.off()
        else:
            return self.on()

    def on(self):
        if self.last_off and datetime.datetime.now() > (self.last_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)):
            return False, {
                'reason': 'needs_cooldown',
                'data': ((self.last_off + datetime.timedelta(minutes=bin.config.PROJECTOR_COOLDOWN_MINUTES)) - datetime.datetime.now()).seconds
            }

        status = self._execute(self.projector_config['commands']['on'])
        if status == 'ON':
            self.running = 'on'
            return True, ''
        return False, {
            'reason': 'bad_data',
            'data': status
        }

    def off(self):
        status = self._execute(self.projector_config['commands']['off'])
        if status == 'OFF':
            self.last_off = datetime.datetime.now()
            self.running = 'off'
            return True, ''
        return False, {
            'reason': 'bad_data',
            'data': status
        }
