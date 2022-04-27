""" Command line tool for sending requests to the terminal """

from datetime import datetime, timezone
from getopt import getopt
from logging import getLogger
from sys import argv
import zmq

from . import common
from .gps303proto import *
from .zmsg import Bcast, Resp

log = getLogger("gps303")


def main(conf, opts, args):
    zctx = zmq.Context()
    zpush = zctx.socket(zmq.PUSH)
    zpush.connect(conf.get("collector", "listenurl"))

    if len(args) < 2:
        raise ValueError("Too few args, need IMEI and command min: " + str(args))
    imei = args[0]
    cmd = args[1]
    args = args[2:]
    cls = class_by_prefix(cmd)
    if isinstance(cls, list):
        raise ValueError("Prefix does not select a single class: " + str(cls))
    kwargs = dict([arg.split("=") for arg in args])
    for arg in args:
        k, v = arg.split("=")
        kwargs[k] = v
    resp = Resp(imei=imei, packet=cls.Out(**kwargs).packed)
    log.debug("Response: %s", resp)
    zpush.send(resp.packed)


if __name__.endswith("__main__"):
    opts, args = getopt(argv[1:], "c:d")
    main(common.init(log, opts=opts), opts, args)
