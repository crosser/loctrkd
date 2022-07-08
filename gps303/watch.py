""" Watch for locevt and print them """

from configparser import ConfigParser
from datetime import datetime, timezone
from logging import getLogger
import zmq

from . import common
from .zx303proto import parse_message
from .zmsg import Bcast

log = getLogger("gps303/watch")


def runserver(conf: ConfigParser) -> None:
    # Is this https://github.com/zeromq/pyzmq/issues/1627 still not fixed?!
    zctx = zmq.Context()  # type: ignore
    zsub = zctx.socket(zmq.SUB)  # type: ignore
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
