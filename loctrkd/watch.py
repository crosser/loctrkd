""" Watch for locevt and print them """

from configparser import ConfigParser
from datetime import datetime, timezone
from importlib import import_module
from logging import getLogger
from typing import Any, cast, List
import zmq

from . import common
from .protomodule import ProtoModule
from .zmsg import Bcast, Rept

log = getLogger("loctrkd/watch")


def runserver(conf: ConfigParser) -> None:
    # Is this https://github.com/zeromq/pyzmq/issues/1627 still not fixed?!
    zctx = zmq.Context()  # type: ignore
    zraw = zctx.socket(zmq.SUB)  # type: ignore
    zraw.connect(conf.get("collector", "publishurl"))
    zraw.setsockopt(zmq.SUBSCRIBE, b"")
    zrep = zctx.socket(zmq.SUB)  # type: ignore
    zrep.connect(conf.get("rectifier", "publishurl"))
    zrep.setsockopt(zmq.SUBSCRIBE, b"")
    poller = zmq.Poller()  # type: ignore
    poller.register(zraw, flags=zmq.POLLIN)
    poller.register(zrep, flags=zmq.POLLIN)

    try:
        while True:
            events = poller.poll(1000)
            for sk, fl in events:
                if sk is zraw:
                    while True:
                        try:
                            zmsg = Bcast(zraw.recv(zmq.NOBLOCK))
                        except zmq.Again:
                            break
                        print(
                            "I" if zmsg.is_incoming else "O",
                            zmsg.proto,
                            zmsg.imei,
                        )
                        pmod = common.pmod_for_proto(zmsg.proto)
                        if pmod is not None:
                            msg = pmod.parse_message(
                                zmsg.packet, zmsg.is_incoming
                            )
                            print(msg)
                            if zmsg.is_incoming and hasattr(msg, "rectified"):
                                print("Rectified:", msg.rectified())
                elif sk is zrep:
                    while True:
                        try:
                            rept = Rept(zrep.recv(zmq.NOBLOCK))
                        except zmq.Again:
                            break
                        print(rept)
                else:
                    print("what is this socket?!", sk)
    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
