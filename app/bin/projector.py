# Imports
import paho.mqtt.client
import bin.exception
import threading
import datetime
import serial
import time
import json
import sys

# Classes
class Projector(threading.Thread):
    def __init__(self, log, config):
        threading.Thread.__init__(self)

        self._log = log
        self._config = config

        self._mqtt = None
        self._serial = None

        self.lock = False

        self.status = 'offline'
        self.running = None
        self.lamp_hours = None
        self.last_off = None
        self.cooldown_left = None

        self._connect_mqtt()
        self._connect_serial()

    def _update_ha(self):
        # sensors
        topic = self._config.MQTT_TOPIC_HOMEASSISTANT.format(component='sensor', name=self._config.PROJECTOR_NAME.lower(), path='lamp_hours/config')
        self._log.debug('Configuring {topic} topic...'.format(topic=topic))
        payload = {
            'availability_topic': self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='status'),
            'qos': 0,
            'device': self._config.DEVICE,
            'state_topic': self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='lamp_hours'),
            'unit_of_measurement': 'hrs',
            'icon': 'hass:clock-time-four',
            'name': '{name} Projector Lamp Hours'.format(name=self._config.PROJECTOR_NAME),
            'unique_id': '{name}.lamp_hours'.format(name=self._config.PROJECTOR_NAME.lower())
        }
        self._mqtt.publish(topic, json.dumps(payload))
        topic = self._config.MQTT_TOPIC_HOMEASSISTANT.format(component='sensor', name=self._config.PROJECTOR_NAME.lower(), path='last_off/config')
        self._log.debug('Configuring {topic} topic...'.format(topic=topic))
        payload = {
            'availability_topic': self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='status'),
            'qos': 0,
            'device': self._config.DEVICE,
            'state_topic': self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='last_off'),
            'icon': 'hass:clock-time-four',
            'name': '{name} Projector Last Off'.format(name=self._config.PROJECTOR_NAME),
            'unique_id': '{name}.last_off'.format(name=self._config.PROJECTOR_NAME.lower())
        }
        self._mqtt.publish(topic, json.dumps(payload))
        topic = self._config.MQTT_TOPIC_HOMEASSISTANT.format(component='sensor', name=self._config.PROJECTOR_NAME.lower(), path='cooldown_left/config')
        self._log.debug('Configuring {topic} topic...'.format(topic=topic))
        payload = {
            'availability_topic': self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='status'),
            'qos': 0,
            'device': self._config.DEVICE,
            'state_topic': self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='cooldown_left'),
            'unit_of_measurement': 'min',
            'icon': 'hass:timer',
            'name': '{name} Projector Cooldown Left'.format(name=self._config.PROJECTOR_NAME),
            'unique_id': '{name}.cooldown_left'.format(name=self._config.PROJECTOR_NAME.lower())
        }
        self._mqtt.publish(topic, json.dumps(payload))

        # switches
        topic = self._config.MQTT_TOPIC_HOMEASSISTANT.format(component='switch', name=self._config.PROJECTOR_NAME.lower(), path='state/config')
        self._log.debug('Configuring {topic} topic...'.format(topic=topic))
        payload = {
            'availability_topic': self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='status'),
            'qos': 0,
            'device': self._config.DEVICE,
            'state_topic': self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='projector'),
            'command_topic': self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='projector/set'),
            'payload_on': 'on',
            'payload_off': 'off',
            'icon': 'hass:projector',
            'name': '{name} Projector'.format(name=self._config.PROJECTOR_NAME),
            'unique_id': '{name}.projector'.format(name=self._config.PROJECTOR_NAME.lower())
        }
        self._mqtt.publish(topic, json.dumps(payload))

    def _connect_mqtt(self):
        self._mqtt = paho.mqtt.client.Client('projector2mqtt')
        self._mqtt.on_connect = self._mqtt_on_connect
        self._mqtt.on_message = self._mqtt_on_message
        
        self._log.info('Connecting to MQTT server...')
        if self._config.MQTT_USERNAME:
            self._log.debug('Setting username/password for access to MQTT server...')
            self._mqtt.username_pw_set(self._config.MQTT_USERNAME, self._config.MQTT_PASSWORD)
            self._log.debug('Username/Password set for access to MQTT server!')
        try:
            self._mqtt.connect(self._config.MQTT_HOST, self._config.MQTT_PORT, self._config.MQTT_TIMEOUT)
        except Exception as ex:
            self._log.error('Unable to connect to MQTT server! Reason: {}'.format(str(ex)))
            sys.exit(4)
        self._log.info('Connected to MQTT server!')
        
        self._log.info('Configuring MQTT topics for HomeAssistant...')
        self._update_ha()
        self._log.info('MQTT topics configured for HomeAssistant!')

        self._mqtt.loop_start()

    def _connect_serial(self):
        self._log.info('Connecting to projector\'s serial port...')
        try:
            self._serial = serial.Serial(
                port=self._config.PROJECTOR_PORT,
                baudrate=self._config.PROJECTOR_CONFIG['baudrate'],
                parity=self._config.PROJECTOR_CONFIG['parity'],
                stopbits=self._config.PROJECTOR_CONFIG['stopbits'],
                bytesize=self._config.PROJECTOR_CONFIG['bytesize'],
                timeout=self._config.SERIAL_TIMEOUT,
                rtscts=False,
                dsrdtr=False
            )
            self.status = 'online'
            self._log.info('Successfully connected to serial port!')
        except Exception as ex:
            self._log.error('Error trying to connect to the projector! Reason: {}'.format(str(ex)))
    
    def _read(self):
        output = ''
        while self._serial.inWaiting() > 0:
            output += self._serial.read(1).decode()
        return output

    def _execute(self, cmd):
        # Access console
        self._serial.write(self._config.PROJECTOR_CONFIG['handshake']['send'].encode())
        time.sleep(self._config.PROJECTOR_CONFIG['handshake']['wait'])
        output = self._read()
        if output != self._config.PROJECTOR_CONFIG['handshake']['expect']:
            raise bin.exception.ProjectorException('Unexpected serial output from the projector! Expecting {} but got {} instead (for {} command).'.format(self._config.PROJECTOR_CONFIG['handshake']['expect'], output, cmd))

        # Execute command
        count = 0
        while True:
            self._serial.write((cmd + self._config.PROJECTOR_CONFIG['handshake']['send']).encode())
            self._log.debug('Command sent to serial device: {}'.format(cmd))
            time.sleep(self._config.PROJECTOR_CONFIG['handshake']['wait'])
            output = self._read()
            self._log.debug('Output received from serial device: {}'.format(output.strip()))
            if output == self._config.PROJECTOR_CONFIG['failed_response']:
                if count >= 1:
                    self._log.warning('Projector returned failed response "{}".'.format(output))
                    raise bin.exception.ProjectorException('Unexpected error when trying to process the returned output: {}!'.format(output))
                else:
                    self._log.warning('Projector returned failed response "{}". Trying again in 5 seconds.'.format(output))
                    time.sleep(1)
                    count += 1
            else:
                return output.strip()[1:-1].split('=')[1]
    
    def _mqtt_on_connect(self, client, data, flags, rc):
        self._log.debug('Connected to MQTT server with result code: {}'.format(str(rc)))
        topic = self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='projector/set/#')
        client.subscribe(topic)
        self._log.debug('Subscribed to {topic} topic...'.format(topic=topic))
    
    def _mqtt_on_message(self, client, data, msg):
        self._log.debug('Topic received: {topic}'.format(topic=msg.topic))
        if msg.topic == self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='projector/set'):
            self._log.info('Received toggle command from HomeAssistant...')
            self._log.debug('Payload received: {}'.format(msg.payload.decode().upper()))
            if msg.payload.decode().upper() == 'ON':
                success, reason = self._on()
                if success:
                    self._log.info('Successfully turned on the projector!')
                else:
                    if reason == 'needs_cooldown':
                        self._log.error('Projector needs to cooldown first! Please wait {} minutes before attempting to power it on!'.format(reason['data'] / 60))
                    elif reason == 'bad_data':
                        self._log.error('Unexpected output from the projector! This is the output it received: {}'.format(reason['data']))

            elif msg.payload.decode().upper() == 'OFF':
                success, reason = self._off()
                if success:
                    self._log.info('Successfully turned off the projector!')
                else:
                    if reason == 'bad_data':
                        self._log.error('Unexpected output from the projector! This is the output it received: {}'.format(reason['data']))

    def _on(self):
        while True:
            if not self.lock:
                break

        if self.last_off and datetime.datetime.now() > (self.last_off + datetime.timedelta(minutes=self._config.PROJECTOR_COOLDOWN_MINUTES)):
            return False, {
                'reason': 'needs_cooldown',
                'data': ((self.last_off + datetime.timedelta(minutes=self._config.PROJECTOR_COOLDOWN_MINUTES)) - datetime.datetime.now()).seconds
            }

        self.lock = True
        status = self._execute(self._config.PROJECTOR_CONFIG['commands']['on'])
        if status == 'ON':
            self.running = 'on'
            self._update_mqtt()
            time.sleep(self._config.PROJECTOR_CONFIG['write_cmd_wait'])
            self.lock = False
            return True, ''
        self.lock = False
        return False, {
            'reason': 'bad_data',
            'data': status
        }
    
    def _off(self):
        while True:
            if not self.lock:
                break

        self.lock = True
        status = self._execute(self._config.PROJECTOR_CONFIG['commands']['off'])
        if status == 'OFF':
            self.last_off = datetime.datetime.now()
            self.running = 'off'
            self._update_mqtt()
            time.sleep(self._config.PROJECTOR_CONFIG['write_cmd_wait'])
            self.lock = False
            return True, ''
        self.lock = False
        return False, {
            'reason': 'bad_data',
            'data': status
        }
    
    def _update_mqtt(self):
        self._log.info('Updating MQTT metrics...')
        # projector2mqtt/<name>/status
        topic = self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='status')
        self._log.debug('Updating {topic} topic...'.format(topic=topic))
        self._mqtt.publish(topic, 'online')
        # projector2mqtt/<name>/projector
        topic = self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='projector')
        self._log.debug('Updating {topic} topic...'.format(topic=topic))
        self._mqtt.publish(topic, self.running)
        # projector2mqtt/<name>/lamp_hours
        topic = self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='lamp_hours')
        self._log.debug('Updating {topic} topic...'.format(topic=topic))
        self._mqtt.publish(topic, self.lamp_hours)
        # projector2mqtt/<name>/last_off
        topic = self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='last_off')
        self._log.debug('Updating {topic} topic...'.format(topic=topic))
        self._mqtt.publish(topic, self.last_off)
        # projector2mqtt/<name>/cooldown_left
        topic = self._config.MQTT_TOPIC_PROJECTOR.format(name=self._config.PROJECTOR_NAME.lower(), path='cooldown_left')
        self._log.debug('Updating {topic} topic...'.format(topic=topic))
        self._mqtt.publish(topic, self.cooldown_left)
        self._log.info('Updated MQTT metrics!')

    def run(self):
        count = 0
        while True:
            if self.status == 'offline':
                self._connect_serial()

            while True:
                if not self.lock:
                    break
            
            try:
                if self.status == 'online':
                    self.lock = True
                    self.cooldown_left = -1
                    if self.last_off and datetime.datetime.now() > (self.last_off + datetime.timedelta(minutes=self._config.PROJECTOR_COOLDOWN_MINUTES)):
                        self.cooldown_left = ((self.last_off + datetime.timedelta(minutes=self._config.PROJECTOR_COOLDOWN_MINUTES)) - datetime.datetime.now()).seconds / 60.0
                    if count % 3 == 0:
                        self.lamp_hours = self._execute(self._config.PROJECTOR_CONFIG['commands']['lamp_hours'])
                    elif count >= 12:
                        self._log.info('Updating MQTT topics for HomeAssistant...')
                        self._update_ha()
                        self._log.info('MQTT topics updated for HomeAssistant!')
                        count = 0
                    output = self._execute(self._config.PROJECTOR_CONFIG['commands']['status'])
                    self.lock = False
                    if output == 'ON':
                        self.running = 'on'
                    elif output == 'OFF':
                        self.running = 'off'
                    else:
                        self.running = None
                        self._log.error('Unable to check power status of the projector! Output received: {}'.format(output))

            except bin.exception.ProjectorException as ex:
                self.status = 'offline'
                self.cooldown_left = None
                self.lamp_hours = None
                self.running = None
                self._log.error(str(ex))
                self.lock = False

            self._update_mqtt()
            count += 1
            time.sleep(5)
