""" Command line tool for sending requests to the terminal """

from configparser import ConfigParser
from datetime import datetime, timezone
from getopt import getopt
from importlib import import_module
from logging import getLogger
from sys import argv
from time import time
from typing import Any, cast, List, Tuple, Type, Union
import zmq

from . import common
from .protomodule import ProtoModule
from .zmsg import Bcast, Resp

log = getLogger("loctrkd")


pmods: List[ProtoModule] = []


def main(
    conf: ConfigParser, opts: List[Tuple[str, str]], args: List[str]
) -> None:
    global pmods
    pmods = [
        cast(ProtoModule, import_module("." + modnm, __package__))
        for modnm in conf.get("collector", "protocols").split(",")
    ]
    # Is this https://github.com/zeromq/pyzmq/issues/1627 still not fixed?!
    zctx = zmq.Context()  # type: ignore
    zpush = zctx.socket(zmq.PUSH)  # type: ignore
    zpush.connect(conf.get("collector", "listenurl"))

    if len(args) < 2:
        raise ValueError(
            "Too few args, need IMEI and command min: " + str(args)
        )
    imei = args[0]
    cmd = args[1]
    args = args[2:]
    handled = False
    for pmod in pmods:
        if pmod.proto_handled(cmd):
            handled = True
            break
    if not handled:
        raise NotImplementedError(f"No protocol can handle {cmd}")
    cls = pmod.class_by_prefix(cmd)
    if isinstance(cls, list):
        raise ValueError("Prefix does not select a single class: " + str(cls))
    kwargs = dict([arg.split("=") for arg in args])
    for arg in args:
        k, v = arg.split("=")
        kwargs[k] = v
    resp = Resp(imei=imei, when=time(), packet=cls.Out(**kwargs).packed)
    log.debug("Response: %s", resp)
    zpush.send(resp.packed)


if __name__.endswith("__main__"):
    opts, args = getopt(argv[1:], "c:d")
    main(common.init(log, opts=opts), opts, args)
