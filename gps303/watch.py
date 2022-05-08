""" Watch for locevt and print them """

from datetime import datetime, timezone
from logging import getLogger
import zmq

from . import common
from .gps303proto import parse_message
from .zmsg import Bcast

log = getLogger("gps303/watch")


def runserver(conf):
    zctx = zmq.Context()
    zsub = zctx.socket(zmq.SUB)
    zsub.connect(conf.get("collector", "publishurl"))
    zsub.setsockopt(zmq.SUBSCRIBE, b"")

    try:
        while True:
            zmsg = Bcast(zsub.recv())
            msg = parse_message(zmsg.packet, zmsg.is_incoming)
            print("I" if zmsg.is_incoming else "O", zmsg.imei, msg)
    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
