""" Watch for locevt and print them """

from datetime import datetime, timezone
from logging import getLogger
from os import umask
from sys import argv, stdin
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
        line = stdin.readline()
        line = line.rstrip("\r\n")
        if not line:
            break
        print(line.encode())
        args = line.split(" ")
        imei = args[0]
        kwargs = dict([arg.split("=") for arg in args[1:]])
        msg = LocEvt(imei=imei, **kwargs)
        print("Publishing:", msg)
        zpub.send(msg.packed)


if __name__.endswith("__main__"):
    main(common.init(log))
