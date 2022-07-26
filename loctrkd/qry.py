""" Print out contens of the event database """

from configparser import ConfigParser
from datetime import datetime, timezone
from getopt import getopt
from importlib import import_module
from logging import getLogger
from sqlite3 import connect
from sys import argv
from typing import Any, cast, List, Tuple

from . import common
from .protomodule import ProtoModule

log = getLogger("loctrkd/qry")


pmods: List[ProtoModule] = []


def main(
    conf: ConfigParser, opts: List[Tuple[str, str]], args: List[str]
) -> None:
    global pmods
    pmods = [
        cast(ProtoModule, import_module("." + modnm, __package__))
        for modnm in conf.get("common", "protocols").split(",")
    ]
    db = connect(conf.get("storage", "dbfn"))
    c = db.cursor()
    if len(args) > 0:
        proto = args[0]
        selector = " where proto = :proto"
    else:
        proto = ""
        selector = ""
    dopts = dict(opts)
    if len(args) > 1 and "-o" in dopts:
        attr = args[1]
        fn = dopts["-o"]
    else:
        attr = ""
        fn = ""

    c.execute(
        """select tstamp, imei, peeraddr, is_incoming, proto, packet
           from events"""
        + selector,
        {"proto": proto},
    )

    for tstamp, imei, peeraddr, is_incoming, proto, packet in c:
        msg: Any = f"Unparseable({packet.hex()})"
        for pmod in pmods:
            if pmod.proto_handled(proto):
                msg = pmod.parse_message(packet, is_incoming)
        print(
            datetime.fromtimestamp(tstamp)
            .astimezone(tz=timezone.utc)
            .isoformat(),
            imei,
            peeraddr,
            msg,
        )
        if fn and hasattr(msg, attr):
            with open(fn, "wb") as fl:  # TODO support multiple files
                fl.write(getattr(msg, attr))


if __name__.endswith("__main__"):
    opts, args = getopt(argv[1:], "o:c:d")
    main(common.init(log, opts=opts), opts, args)
