""" Generate and publish locevt from the text input """

import atexit
from datetime import datetime, timezone
from logging import getLogger
from os import path, umask
from readline import read_history_file, set_history_length, write_history_file
from sys import argv
import zmq

from . import common
from .zmsg import LocEvt

log = getLogger("gps303/watch")

RL_HISTORY = path.join(path.expanduser("~"), ".gps303_history")

def main(conf):
    zctx = zmq.Context()
    zpub = zctx.socket(zmq.PUB)
    oldmask = umask(0o117)
    zpub.bind(conf.get("lookaside", "publishurl"))
    umask(oldmask)
    try:
        read_history_file(RL_HISTORY)
    except FileNotFoundError:
        pass
    set_history_length(1000)
    atexit.register(write_history_file, RL_HISTORY)

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
