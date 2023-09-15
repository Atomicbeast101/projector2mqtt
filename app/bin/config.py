# Imports
import traceback
import logging
import serial
import socket
import sys
import os
import re

### Environmental Variables ###
# LOG_LEVEL = INFO
# LOG_PATH = /logs
# LOG_RETENTION_DAYS = 5
# PROJECTOR_BRAND = benq
# PROJECTOR_MODEL = TK700
# PROJECTOR_PORT = /dev/ttyUSB0
# PROJECTOR_COOLDOWN_MINUTES = 10
# PROJECTOR_UNIQUE_ID = <UNIQUE_ID>
# MQTT_HOST = <HOST>
# MQTT_PORT = 1883
# MQTT_USERNAME = <BLANK_IF_NOT_USED>
# MQTT_PASSWORD = <BLANK_IF_NOT_USED>

# Attributes
SERIAL_TIMEOUT = 1
SUPPORTED_PROJECTORS = {
    'benq': {
        # https://esupportdownload.benq.com/esupport/PROJECTOR/Control%20Protocols/TK700STi/TK700STi_RS232%20Control%20Guide_0_Windows10_Windows7_Windows8.pdf
        'tk700': {
            'baudrate': 115200,
            'bytesize': serial.EIGHTBITS,
            'parity': serial.PARITY_NONE,
            'stopbits': serial.STOPBITS_ONE,
            'commands': {
                'model': '*modelname=?#',
                'lamp_hours': '*ltim=?#',
                'status': '*pow=?#',
                'on': '*pow=on#',
                'off': '*pow=off#'
            },
            'handshake': {
                'send': '\r',
                'wait': 1,
                'expect': '>'
            }
        }
    }
}
SUPPORTED_DEVICES_URL = '[TODO_HERE]'
PROJECTOR_UNQIUE_ID_PATTERN = re.compile('[A-Za-z0-9_-]+')

# Class
class Config:
    def __init__(self, log):
        self.log = log

        # Attributes
        self.PROJECTOR_BRANDS = ['benq']
        self.LOG_LEVEL = 'INFO'
        self.LOG_PATH = '/logs'
        self.LOG_RETENTION_DAYS = 5
        self.PROJECTOR_BRAND = 'benq'
        self.PROJECTOR_MODEL = 'tk700'
        self.PROJECTOR_PORT = '/dev/ttyUSB0'
        self.PROJECTOR_COOLDOWN_MINUTES = 10
        self.PROJECTOR_NAME = ''
        self.MQTT_HOST = 'localhost'
        self.MQTT_PORT = 1883
        self.MQTT_USERNAME = ''
        self.MQTT_PASSWORD = ''
        self.MQTT_TIMEOUT = 60
        
        try:
            # Validate LOG_LEVEL
            self.LOG_LEVEL = os.environ['LOG_LEVEL'] if 'LOG_LEVEL' in os.environ else self.LOG_LEVEL
            if self.LOG_LEVEL.upper() not in list(logging._nameToLevel.keys()):
                log.error('Invalid LOG_LEVEL value! It must be one of the following options: {}'.format(', '.format(list(logging._nameToLevel.keys()))))
            # Validate LOG_PATH
            self.LOG_PATH = os.environ['LOG_PATH'] if 'LOG_PATH' in os.environ else self.LOG_PATH
            if not os.path.exists(self.LOG_PATH):
                log.error('{} log path does not exist! Please create one.'.format(self.LOG_PATH))
                sys.exit(4)
            # Validate LOG_RETENTION_DAYS
            self.LOG_RETENTION_DAYS = os.environ['LOG_RETENTION_DAYS'] if 'LOG_RETENTION_DAYS' in os.environ else self.LOG_RETENTION_DAYS
            if str(self.LOG_RETENTION_DAYS).isnumeric():
                if not int(self.LOG_RETENTION_DAYS) >= 1:
                    log.error('Invalid LOG_RETENTION_DAYS number! It must be greater then or equal to 1.')
                    sys.exit(4)
            else:
                log.error('Invalid LOG_RETENTION_DAYS value! It must be numeric and greater than or equal to 1.')
                sys.exit(4)
            # Validate PROJECTOR_BRAND
            self.PROJECTOR_BRAND = os.environ['PROJECTOR_BRAND'] if 'PROJECTOR_BRAND' in os.environ else self.PROJECTOR_BRAND
            if self.PROJECTOR_BRAND.lower() not in SUPPORTED_PROJECTORS:
                log.error('This brand is not supported by the controller! Please check here for the supported list: {}'.format(SUPPORTED_DEVICES_URL))
                sys.exit(4)
            # Validate PROJECTOR_MODEL
            self.PROJECTOR_MODEL = os.environ['PROJECTOR_MODEL'] if 'PROJECTOR_MODEL' in os.environ else self.PROJECTOR_MODEL
            if self.PROJECTOR_MODEL.lower() not in SUPPORTED_PROJECTORS[self.PROJECTOR_BRAND.lower()]:
                log.error('This {} model is not supported by the controller! Please check here for the supported list: {}'.format(self.PROJECTOR_BRAND.lower(), SUPPORTED_DEVICES_URL))
                sys.exit(4)
            # Validate PROJECTOR_PORT
            self.PROJECTOR_PORT = os.environ['PROJECTOR_PORT'] if 'PROJECTOR_PORT' in os.environ else self.PROJECTOR_PORT
            # Validate PROJECTOR_COOLDOWN_MINUTES
            self.PROJECTOR_COOLDOWN_MINUTES = os.environ['PROJECTOR_COOLDOWN_MINUTES'] if 'PROJECTOR_COOLDOWN_MINUTES' in os.environ else self.PROJECTOR_COOLDOWN_MINUTES
            if str(self.PROJECTOR_COOLDOWN_MINUTES).isnumeric():
                if int(self.PROJECTOR_COOLDOWN_MINUTES) < 1:
                    log.error('Invalid PROJECTOR_COOLDOWN_MINUTES number! It must be greater then or equal to 1.')
                    sys.exit(4)
            else:
                log.error('Invalid PROJECTOR_COOLDOWN_MINUTES value! It must be numeric and greater than or equal to 1.')
                sys.exit(4)
            # Validate PROJECTOR_NAME
            self.PROJECTOR_NAME = os.environ['PROJECTOR_NAME'] if 'PROJECTOR_NAME' in os.environ else None
            if self.PROJECTOR_NAME:
                if not PROJECTOR_UNQIUE_ID_PATTERN.fullmatch(self.PROJECTOR_NAME):
                    log.error('Invalid PROJECTOR_NAME value! It must only use A-Z, 0-9, _ and - characters.')
                    sys.exit(4)
            elif not self.PROJECTOR_NAME:
                log.error('Invalid PROJECTOR_NAME value! Please populate a unique ID for this projector you want to control. It can be a brand/model or a name & location. Only A-Z, _ and - characters are permitted.')
                sys.exit(4)
            # Validate MQTT_HOST
            self.MQTT_HOST = os.environ['MQTT_HOST'] if 'MQTT_HOST' in os.environ else None
            if self.MQTT_HOST:
                try:
                    socket.gethostbyname(self.MQTT_HOST)
                except Exception as ex:
                    log.error('Invalid MQTT_HOST value! Please put in the correct hostname or IP of the MQTT server that HomeAssistant uses.')
            else:
                log.error('Invalid MQTT_HOST value! Please put in a host or IP of the MQTT server that HomeAssistant uses.')
                sys.exit(4)
            # Validate MQTT_PORT
            self.MQTT_PORT = os.environ['MQTT_PORT'] if 'MQTT_PORT' in os.environ else self.MQTT_PORT
            if str(self.MQTT_PORT).isnumeric():
                if not (1 < int(self.MQTT_PORT) <= 65535):
                    log.error('Invalid MQTT_PORT number! It must be between 2 and 65535.')
                    sys.exit(4)
            else:
                log.error('Invalid MQTT_PORT value! It must be numeric value and be between 2 and 65535.')
                sys.exit(4)
            # Validate MQTT_USERNAME
            self.MQTT_USERNAME = os.environ['MQTT_USERNAME'] if 'MQTT_USERNAME' in os.environ else None
            # Validate MQTT_PASSWORD
            self.MQTT_PASSWORD = os.environ['MQTT_PASSWORD'] if 'MQTT_PASSWORD' in os.environ else None
            if (not self.MQTT_USERNAME and self.MQTT_PASSWORD) or (self.MQTT_USERNAME and not self.MQTT_PASSWORD):
                log.error('Both MQTT_USERNAME and MQTT_PASSWORD has to be populated if you are using authentication!')
                sys.exit(4)
            # Validate MQTT_TIMEOUT
            self.MQTT_TIMEOUT = os.environ['MQTT_TIMEOUT'] if 'MQTT_TIMEOUT' in os.environ else self.MQTT_TIMEOUT
            if str(self.MQTT_TIMEOUT).isnumeric():
                if int(self.MQTT_TIMEOUT) < 1:
                    log.error('Invalid MQTT_TIMEOUT number! It must be greater then or equal to 1.')
                    sys.exit(4)
            else:
                log.error('Invalid MQTT_TIMEOUT value! It must be numeric and greater than or equal to 1.')
                sys.exit(4)

        except Exception as ex:
            log.error('Unable to load config file! Reason: {}\nStacktrace:\n{}'.format(str(ex), traceback.format_exc()))
            sys.exit(4)
