# default logger
from Utilities import Logger
logger = Logger.getLogger('default', 'logs', False)

# config
from Configure import Config
config = Config("Config.ini")

from Core.CoreManager import *