""" Watch for locevt and print them """

from datetime import datetime, timezone
from logging import getLogger
import zmq

from . import common
from .zmsg import LocEvt

log = getLogger("gps303/watch")


def runserver(conf):
    zctx = zmq.Context()
    zsub = zctx.socket(zmq.SUB)
    zsub.connect(conf.get("lookaside", "publishurl"))
    zsub.setsockopt(zmq.SUBSCRIBE, b"")

    try:
        while True:
            zmsg = LocEvt(zsub.recv())
            print(zmsg)
    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
