""" Store zmq broadcasts to sqlite """

from configparser import ConfigParser
from datetime import datetime, timezone
from logging import getLogger
import zmq

from . import common
from .evstore import initdb, stow
from .zx303proto import proto_of_message
from .zmsg import Bcast

log = getLogger("loctrkd/storage")


def runserver(conf: ConfigParser) -> None:
    dbname = conf.get("storage", "dbfn")
    log.info('Using Sqlite3 database "%s"', dbname)
    initdb(dbname)
    # Is this https://github.com/zeromq/pyzmq/issues/1627 still not fixed?!
    zctx = zmq.Context()  # type: ignore
    zsub = zctx.socket(zmq.SUB)  # type: ignore
    zsub.connect(conf.get("collector", "publishurl"))
    zsub.setsockopt(zmq.SUBSCRIBE, b"")

    try:
        while True:
            zmsg = Bcast(zsub.recv())
            log.debug(
                "%s IMEI %s from %s at %s: %s",
                "I" if zmsg.is_incoming else "O",
                zmsg.imei,
                zmsg.peeraddr,
                datetime.fromtimestamp(zmsg.when).astimezone(tz=timezone.utc),
                zmsg.packet.hex(),
            )
            stow(
                is_incoming=zmsg.is_incoming,
                peeraddr=str(zmsg.peeraddr),
                when=zmsg.when,
                imei=zmsg.imei,
                proto=proto_of_message(zmsg.packet),
                packet=zmsg.packet,
            )
    except KeyboardInterrupt:
        zsub.close()
        zctx.destroy()  # type: ignore


if __name__.endswith("__main__"):
    runserver(common.init(log))
