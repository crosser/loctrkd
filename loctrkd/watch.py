""" Watch for locevt and print them """

from configparser import ConfigParser
from datetime import datetime, timezone
from importlib import import_module
from logging import getLogger
from typing import Any, cast, List
import zmq

from . import common
from .protomodule import ProtoModule
from .zmsg import Bcast

log = getLogger("loctrkd/watch")


def runserver(conf: ConfigParser) -> None:
    # Is this https://github.com/zeromq/pyzmq/issues/1627 still not fixed?!
    zctx = zmq.Context()  # type: ignore
    zsub = zctx.socket(zmq.SUB)  # type: ignore
    zsub.connect(conf.get("collector", "publishurl"))
    zsub.setsockopt(zmq.SUBSCRIBE, b"")

    try:
        while True:
            zmsg = Bcast(zsub.recv())
            print("I" if zmsg.is_incoming else "O", zmsg.proto, zmsg.imei)
            pmod = common.pmod_for_proto(zmsg.proto)
            if pmod is not None:
                msg = pmod.parse_message(zmsg.packet, zmsg.is_incoming)
                print(msg)
                if zmsg.is_incoming and hasattr(msg, "rectified"):
                    print(msg.rectified())
    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
