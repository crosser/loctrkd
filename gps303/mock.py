""" Watch for locevt and print them """

from datetime import datetime, timezone
from logging import getLogger
from os import umask
import readline
from sys import argv
import zmq

from . import common
from .zmsg import LocEvt

log = getLogger("gps303/watch")


def main(conf):
    zctx = zmq.Context()
    zpub = zctx.socket(zmq.PUB)
    oldmask = umask(0o117)
    zpub.bind(conf.get("lookaside", "publishurl"))
    umask(oldmask)

    while True:
        try:
            line = input("> ")
        except EOFError:
            break
        line = line.rstrip("\r\n")
        args = line.split(" ")
        imei = args[0]
        kwargs = dict([arg.split("=") for arg in args[1:]])
        msg = LocEvt(imei=imei, **kwargs)
        print("Publishing:", msg)
        zpub.send(msg.packed)


if __name__.endswith("__main__"):
    main(common.init(log))
