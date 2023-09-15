# Imports
import paho.mqtt.publish
import paho.mqtt.client
import logging.handlers
import bin.projector
import bin.config
import threading
import logging
import time
import json
import sys
import os

# Attributes
LOG_FORMAT = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
PROJECTOR_MQTT_TOPIC = 'projector/{name}/{type}'
HOMEASSISTANT_MQTT_TOPIC = 'homeassistant/{component}/projector-{name}/{path}'
config = None
log = None
proj = None
mqttclient = None
DEVICE = {}

# Functions
def setup_console_logging():
    global log
    log = logging.getLogger()
    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(LOG_FORMAT)
    log.addHandler(consoleHandler)

def load_config():
    global config
    config = bin.config.Config(log)

def setup_file_logging():
    log.setLevel(logging.getLevelName(config.LOG_LEVEL))
    fileHandler = logging.handlers.TimedRotatingFileHandler(os.path.join(config.LOG_PATH, 'activity.log'),
                                                        when="d",
                                                        interval=1,
                                                        backupCount=config.LOG_RETENTION_DAYS)
    fileHandler.setFormatter(LOG_FORMAT)
    log.addHandler(fileHandler)

def setup_projector():
    global proj
    try:
        proj = bin.projector.Projector(config.PROJECTOR_BRAND.lower(), config.PROJECTOR_MODEL.lower(), config.PROJECTOR_PORT, log)
    except bin.projector.ProjectorException as ex:
        log.error('Error trying to load the projector. Reason: {}'.format(str(ex)))
        sys.exit(4)

def setup_mqtt():
    global mqttclient

    mqttclient = paho.mqtt.client.Client(config.PROJECTOR_NAME)
    mqttclient.on_connect = on_connect
    mqttclient.on_message = on_message
    if config.MQTT_USERNAME:
        mqttclient.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
    try:
        mqttclient.connect(config.MQTT_HOST, config.MQTT_PORT, config.MQTT_TIMEOUT)
    except Exception as ex:
        log.error('Unable to connect to MQTT server! Reason: {}'.format(str(ex)))
        sys.exit(4)

# MQTT Functions
def on_connect(client, userdata, flags, rc):
    global mqttclient

    log.info('Connected to MQTT with result code: {code}'.format(code=str(rc)))
    mqttclient.subscribe('projector/{name}/set/#'.format(name=config.PROJECTOR_NAME.lower()))

def on_message(client, userdata, msg):
    global mqttclient

    if msg.topic == 'projector/{name}/set/#'.format(name=config.PROJECTOR_NAME.lower()):
        log.info('Received toggle command from HomeAssistant...')
        if msg.payload == 'ON':
            success, reason = proj.on()
            if success:
                log.info('Successfully turned on the projector!')
            else:
                if reason == 'needs_cooldown':
                    log.error('Projector needs to cooldown first! Please wait {} minutes before attempting to power it on!'.format(reason['data'] / 60))
                elif reason == 'bad_data':
                    log.error('Unexpected output from the projector! This is the output it received: {}'.format(reason['data']))

        if msg.payload == 'OFF':
            success, reason = proj.off()
            if success:
                log.info('Successfully turned off the projector!')
            else:
                if reason == 'bad_data':
                    log.error('Unexpected output from the projector! This is the output it received: {}'.format(reason['data']))

        topic = PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='state')
        payload = {
            'status': proj.status()['power_on'],
            'lamp_hours': proj.status()['lamp_hours'],
            'last_turned_off': proj.status()['last_turned_off'],
            'cooldown_left': proj.status()['cooldown_left']
        }
        mqttclient.publish(topic, json.dumps(payload))

def configure_homeassistant():
    global mqttclient

    # homeassistant/binary_sensor/projector-<name>/status/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='binary_sensor', name=config.PROJECTOR_NAME.lower(), path='status/config')
    payload = {
        'unique_id': 'projector-{name}-status'.format(name=config.PROJECTOR_NAME.lower()),
        'name': '{name} Projector Power Status'.format(name=config.PROJECTOR_NAME),
        'state_topic': 'projector/{name}/state'.format(name=config.PROJECTOR_NAME.lower()),
        'icon': 'hass:projector',
        'value_template': '{{ value_json.status }}'
    }
    mqttclient.publish(topic, json.dumps(payload))
    # homeassistant/sensor/projector-<name>/lamp_hours/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='sensor', name=config.PROJECTOR_NAME.lower(), path='lamp_hours/config')
    payload = {
        'unique_id': 'projector-{name}-lamp-hours'.format(name=config.PROJECTOR_NAME.lower()),
        'name': '{name} Projector Lamp Hours'.format(name=config.PROJECTOR_NAME),
        'state_topic': 'projector/{name}/state'.format(name=config.PROJECTOR_NAME.lower()),
        'unit_of_measurement': 'hrs',
        'icon': 'hass:clock-time-four',
        'value_template': '{{ value_json.lamp_hours }}'
    }
    mqttclient.publish(topic, json.dumps(payload))
    # homeassistant/sensor/projector-<name>/last_off/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='sensor', name=config.PROJECTOR_NAME.lower(), path='last_off/config')
    payload = {
        'unique_id': 'projector-{name}-last-off'.format(name=config.PROJECTOR_NAME.lower()),
        'name': '{name} Projectors Last Power Timestamp'.format(name=config.PROJECTOR_NAME),
        'state_topic': 'projector/{name}/state'.format(name=config.PROJECTOR_NAME.lower()),
        'unit_of_measurement': '',
        'icon': 'hass:clock-time-four',
        'value_template': '{{ value_json.last_off }}'
    }
    mqttclient.publish(topic, json.dumps(payload))
    # homeassistant/sensor/projector-<name>/cooldown/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='sensor', name=config.PROJECTOR_NAME.lower(), path='cooldown/config')
    payload = {
        'unique_id': 'projector-{name}-cooldown'.format(name=config.PROJECTOR_NAME.lower()),
        'name': '{name} Projector Cooldown Time Left'.format(name=config.PROJECTOR_NAME),
        'state_topic': 'projector/{name}/state'.format(name=config.PROJECTOR_NAME.lower()),
        'unit_of_measurement': 's',
        'icon': 'hass:timer',
        'value_template': '{{ value_json.cooldown_left }}'
    }
    mqttclient.publish(topic, json.dumps(payload))
    # homeassistant/switch/projector-<name>/state
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='switch', name=config.PROJECTOR_NAME.lower(), path='state')
    payload = {
        'name': '{name} Projector'.format(name=config.PROJECTOR_NAME),
        'icon': 'hass:projector',
        'state_topic': 'projector/{name}/state'.format(name=config.PROJECTOR_NAME.lower()),
        'command_topic': 'projector/{name}/set'.format(name=config.PROJECTOR_NAME.lower()),
        'value_template': '{{ value_json.cooldown_left }}'
    }
    mqttclient.publish(topic, json.dumps(payload))

def update_state():
    global mqttclient

    while True:
        topic = PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='state')
        status = proj.status()
        payload = {
            'status': status['power_on'],
            'lamp_hours': status['lamp_hours'],
            'last_turned_off': status['last_turned_off'],
            'cooldown_left': status['cooldown_left']
        }
        mqttclient.publish(topic, json.dumps(payload))
        time.sleep(5)

# Main
def main():
    global proj
    setup_console_logging()
    load_config()
    setup_file_logging()
    setup_projector()
    setup_mqtt()
    configure_homeassistant()
    log.info('Starting projector status updater thread...')
    threading.Thread(target=proj.updater, daemon=True, name='ProjectorStatusUpdater')
    log.info('Listening for requests from HomeAssistant...')
    update_state()

main()
