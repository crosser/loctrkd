""" Store zmq broadcasts to sqlite """

from getopt import getopt
from logging import getLogger
from logging.handlers import SysLogHandler
import sys
from time import time
import zmq

from . import common
from .evstore import initdb, stow
from .gps303proto import parse_message

log = getLogger("gps303/storage")

def runserver(conf):
    dbname = conf.get("storage", "dbfn")
    log.info('Using Sqlite3 database "%s"', dbname)
    initdb(dbname)
    zctx = zmq.Context()
    zsub = zctx.socket(zmq.SUB)
    zsub.connect(conf.get("collector", "publishurl"))
    zsub.setsockopt(zmq.SUBSCRIBE, b"")

    try:
        while True:
            zmsg = zsub.recv()
            imei = zmsg[1:17].decode()
            packet = zmsg[17:]
            msg = parse_message(packet)
            log.debug("From IMEI %s: %s", imei, msg)
            stow("", time(), imei, msg.length, msg.PROTO, msg.payload)
    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
