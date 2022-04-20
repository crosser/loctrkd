""" Store zmq broadcasts to sqlite """

from datetime import datetime, timezone
from getopt import getopt
from logging import getLogger
from logging.handlers import SysLogHandler
import sys
from time import time
import zmq

from . import common
from .evstore import initdb, stow
from .gps303proto import parse_message
from .zmsg import Bcast

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
            zmsg = Bcast(zsub.recv())
            msg = parse_message(zmsg.packet)
            log.debug("IMEI %s from %s at %s: %s", zmsg.imei, zmsg.peeraddr, datetime.fromtimestamp(zmsg.when).astimezone(tz=timezone.utc), msg)
            if zmsg.peeraddr is not None:
                addr, port = zmsg.peeraddr
                peeraddr = str(addr), port
            else:
                peeraddr = None
            stow(
                peeraddr,
                zmsg.when,
                zmsg.imei,
                msg.length,
                msg.PROTO,
                msg.payload,
            )
    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
