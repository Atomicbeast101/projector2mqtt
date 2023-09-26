# Imports
import logging.handlers
import bin.projector
import bin.config
import logging
import sys
import os

# Attributes
LOG_FORMAT = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Functions
def get_console_logging():
    log = logging.getLogger()
    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(LOG_FORMAT)
    log.addHandler(consoleHandler)
    return log

def set_file_logging(log, config):
    log.setLevel(logging.getLevelName(config.LOG_LEVEL))
    fileHandler = logging.handlers.TimedRotatingFileHandler(os.path.join(config.LOG_PATH, 'activity.log'),
                                                        when="d",
                                                        interval=1,
                                                        backupCount=config.LOG_RETENTION_DAYS)
    fileHandler.setFormatter(LOG_FORMAT)
    log.addHandler(fileHandler)
    return log

# Main
def main():
    log = get_console_logging()

    log.info('Loading configuration...')
    config = bin.config.Config(log)
    log.info('Configuration loaded!')

    log.info('Configuring file logging...')
    log = set_file_logging(log, config)
    log.info('File logging configured!')

    log.info('Starting up Projector updater...')
    projector = bin.projector.Projector(log, config)
    projector.start()
    projector.join()

main()
