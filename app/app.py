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
PROJECTOR_MQTT_TOPIC = 'projector2mqtt/{name}/{path}'
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
        'name': '{brand} {model}'.format(brand=config.PROJECTOR_BRAND, model=config.PROJECTOR_MODEL),
        'manufacturer': config.PROJECTOR_BRAND,
        'model': config.PROJECTOR_MODEL,
        'identifiers': config.PROJECTOR_NAME,
        'via_device': 'projector2mqtt'
    }

    mqttclient = paho.mqtt.client.Client('projector2mqtt')
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
    log.info('Connected to MQTT with result code: {}'.format(str(rc)))
    client.subscribe(PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='projector/set/#'))

def on_message(client, userdata, msg):
    log.debug('Topic received: {topic}'.format(topic=msg.topic))
    if msg.topic == PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='projector/set'):
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

def configure_homeassistant():
    # sensors
    # homeassistant/sensor/projector2mqtt-<name>/lamp_hours/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='sensor', name=config.PROJECTOR_NAME.lower(), path='lamp_hours/config')
    payload = {
        'availability_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='status'),
        'qos': 0,
        'device': DEVICE,
        'state_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='lamp_hours'),
        'unit_of_measurement': 'hrs',
        'icon': 'hass:clock-time-four',
        'name': '{name} Projector Lamp Hours'.format(name=config.PROJECTOR_NAME),
        'unique_id': '{name}.lamp_hours'.format(name=config.PROJECTOR_NAME.lower())
    }
    mqttclient.publish(topic, json.dumps(payload))
    # homeassistant/sensor/projector2mqtt-<name>/last_off/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='sensor', name=config.PROJECTOR_NAME.lower(), path='last_off/config')
    payload = {
        'availability_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='status'),
        'qos': 0,
        'device': DEVICE,
        'state_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='last_off'),
        'icon': 'hass:clock-time-four',
        'name': '{name} Projector Last Off'.format(name=config.PROJECTOR_NAME),
        'unique_id': '{name}.last_off'.format(name=config.PROJECTOR_NAME.lower())
    }
    mqttclient.publish(topic, json.dumps(payload))
    # homeassistant/sensor/projector2mqtt-<name>/cooldown_left/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='sensor', name=config.PROJECTOR_NAME.lower(), path='cooldown_left/config')
    payload = {
        'availability_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='status'),
        'qos': 0,
        'device': DEVICE,
        'state_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='cooldown_left'),
        'unit_of_measurement': 'min',
        'icon': 'hass:timer',
        'name': '{name} Projector Cooldown Left'.format(name=config.PROJECTOR_NAME),
        'unique_id': '{name}.cooldown_left'.format(name=config.PROJECTOR_NAME.lower())
    }
    mqttclient.publish(topic, json.dumps(payload))

    # switches
    # homeassistant/switch/projector2mqtt-<name>/state/config
    topic = HOMEASSISTANT_MQTT_TOPIC.format(component='switch', name=config.PROJECTOR_NAME.lower(), path='state/config')
    payload = {
        'availability_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='status'),
        'qos': 0,
        'device': DEVICE,
        'state_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='projector'),
        'command_topic': PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='projector/set'),
        'payload_on': 'on',
        'payload_off': 'off',
        'icon': 'hass:projector',
        'name': '{name} Projector'.format(name=config.PROJECTOR_NAME),
        'unique_id': '{name}.projector'.format(name=config.PROJECTOR_NAME.lower())
    }
    mqttclient.publish(topic, json.dumps(payload))

def update_metrics():
    status = proj.status()

    # projector2mqtt/<name>/status
    topic = PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='status')
    mqttclient.publish(topic, 'online')
    # projector2mqtt/<name>/projector
    topic = PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='projector')
    mqttclient.publish(topic, status['running'])
    # projector2mqtt/<name>/lamp_hours
    topic = PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='lamp_hours')
    mqttclient.publish(topic, status['lamp_hours'])
    # projector2mqtt/<name>/last_off
    topic = PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='last_off')
    mqttclient.publish(topic, status['last_off'])
    # projector2mqtt/<name>/cooldown_left
    topic = PROJECTOR_MQTT_TOPIC.format(name=config.PROJECTOR_NAME.lower(), path='cooldown_left')
    mqttclient.publish(topic, status['cooldown_left'])

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
