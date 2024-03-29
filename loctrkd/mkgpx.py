""" Example that produces gpx from events in evstore """

# run as:
# python -m loctrkd.mkgpx <IMEI>
# Generated gpx is emitted to stdout

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

log = getLogger("loctrkd/mkgpx")


def main(
    conf: ConfigParser, opts: List[Tuple[str, str]], args: List[str]
) -> None:
    db = connect(conf.get("storage", "dbfn"))
    c = db.cursor()
    c.execute(
        """select tstamp, is_incoming, proto, packet from events
           where imei = ?  and is_incoming = true
           and proto in (?, ?)
           order by tstamp""",
        (args[0], "BS:UD", "BS:UD2"),
    )
    print(
        """<?xml version="1.0"?>
    <gpx version="1.1"
    creator="loctrkd"
    xmlns="http://www.topografix.com/GPX/1/1">
      <name>Location Data</name>
      <trk>
        <name>Location Data</name>
        <trkseg>
    """
    )

    for tstamp, is_incoming, proto, packet in c:
        pmod = common.pmod_for_proto(proto)
        if pmod is not None:
            msg = pmod.parse_message(packet, is_incoming=is_incoming)
        lat, lon = msg.latitude, msg.longitude
        isotime = (
            datetime.fromtimestamp(tstamp)
            .astimezone(tz=timezone.utc)
            .isoformat()
        )
        isotime = isotime[: isotime.rfind(".")] + "Z"
        trkpt = """      <trkpt lat="{}" lon="{}">
              <time>{}</time>
          </trkpt>""".format(
            lat, lon, isotime
        )
        print(trkpt)
        if False:
            print(
                datetime.fromtimestamp(tstamp)
                .astimezone(tz=timezone.utc)
                .isoformat(),
                msg,
            )
    print(
        """    </trkseg>
      </trk>
    </gpx>"""
    )


if __name__.endswith("__main__"):
    opts, args = getopt(argv[1:], "o:c:d")
    main(common.init(log, opts=opts), opts, args)
