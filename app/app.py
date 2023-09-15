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
PROJECTOR_MQTT_TOPIC = 'projector2mqtt/{name}/{type}'
HOMEASSISTANT_MQTT_TOPIC = 'homeassistant/{component}/projector2mqtt-{name}/{path}'
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
    global DEVICE, mqttclient

    DEVICE = {
        'name': '{brand} {model}'.format(config.PROJECTOR_BRAND, config.PROJECTOR_MODEL),
        'manufacturer': config.PROJECTOR_BRAND,
        'model': config.PROJECTOR_MODEL,
        'identifiers': config.PROJECTOR_NAME,
        'via_device': 'projector2mqtt'
    }

    mqttclient = paho.mqtt.client.Client('projector2mqtt')
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
    if msg.topic == '{}/#'.format(PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='set')):
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

        update_metrics()

def configure_homeassistant():
    global mqttclient

    # binary_sensors
    # homeassistant/binary_sensor/projector2mqtt-<name>/status/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='binary_sensor', name=config.PROJECTOR_NAME.lower(), path='projector/config')
    payload = {
        'availability_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='status'),
        'qos': 0,
        'device': DEVICE,
        'state_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='status'),
        'payload_on': 'on',
        'payload_off': 'off',
        'icon': 'hass:projector',
        'name': '{name} Projector'.format(name=config.PROJECTOR_NAME),
        'unique_id': '{name}_projector.status'.format(name=config.PROJECTOR_NAME.lower())
    }
    mqttclient.publish(topic, json.dumps(payload))

    # sensors
    # homeassistant/sensor/projector2mqtt-<name>/lamp_hours/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='sensor', name=config.PROJECTOR_NAME.lower(), path='lamp_hours/config')
    payload = {
        'availability_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='state'),
        'qos': 0,
        'device': DEVICE,
        'state_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='state'),
        'value_template': '{{ value_json.lamp_hours }}',
        'unit_of_measurement': 'hrs',
        'icon': 'hass:clock-time-four',
        'name': '{name} Projector'.format(name=config.PROJECTOR_NAME),
        'unique_id': '{name}_projector.lamp_hours'.format(name=config.PROJECTOR_NAME.lower())
    }
    mqttclient.publish(topic, json.dumps(payload))
    # homeassistant/sensor/projector2mqtt-<name>/last_off/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='sensor', name=config.PROJECTOR_NAME.lower(), path='last_off/config')
    payload = {
        'availability_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='state'),
        'qos': 0,
        'device': DEVICE,
        'state_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='state'),
        'value_template': '{{ value_json.last_off }}',
        'icon': 'hass:clock-time-four',
        'name': '{name} Projector'.format(name=config.PROJECTOR_NAME),
        'unique_id': '{name}_projector.last_off'.format(name=config.PROJECTOR_NAME.lower())
    }
    mqttclient.publish(topic, json.dumps(payload))
    # homeassistant/sensor/projector2mqtt-<name>/cooldown/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='sensor', name=config.PROJECTOR_NAME.lower(), path='cooldown/config')
    payload = {
        'availability_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='state'),
        'qos': 0,
        'device': DEVICE,
        'state_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='state'),
        'value_template': '{{ value_json.cooldown_left }}',
        'unit_of_measurement': 'min',
        'icon': 'hass:timer',
        'name': '{name} Projector'.format(name=config.PROJECTOR_NAME),
        'unique_id': '{name}_projector.cooldown_left'.format(name=config.PROJECTOR_NAME.lower())
    }
    mqttclient.publish(topic, json.dumps(payload))

    # switches
    # homeassistant/switch/projector2mqtt-<name>/state
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='switch', name=config.PROJECTOR_NAME.lower(), path='state')
    payload = {
        'availability_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='status'),
        'qos': 0,
        'device': DEVICE,
        'state_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='status'),
        'command_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='set'),
        'icon': 'hass:projector',
        'name': '{name} Projector'.format(name=config.PROJECTOR_NAME),
        'unique_id': '{name}.projector'.format(name=config.PROJECTOR_NAME.lower())
    }
    mqttclient.publish(topic, json.dumps(payload))

def update_metrics():
    global mqttclient

    # projector2mqtt/<name>/status
    topic = PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='status')
    status = proj.status()
    payload = 'off'
    if status['power_on']:
        payload = 'on'
    mqttclient.publish(topic, payload)

    # projector2mqtt/<name>/config
    topic = PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='config')
    payload = {
        'device_name': config.PROJECTOR_NAME,
        'device_type': '{brand} {model}'.format(config.PROJECTOR_BRAND, config.PROJECTOR_MODEL)
    }
    mqttclient.publish(topic, json.dumps(payload))

    # projector2mqtt/<name>/state
    topic = PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), type='state')
    status = proj.status()
    payload = {
        'lamp_hours': status['lamp_hours'],
        'last_turned_off': status['last_turned_off'],
        'cooldown_left': status['cooldown_left']
    }
    mqttclient.publish(topic, json.dumps(payload))

def update_state():
    while True:
        update_metrics()
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
