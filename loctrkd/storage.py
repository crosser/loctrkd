""" Store zmq broadcasts to sqlite """

from configparser import ConfigParser
from datetime import datetime, timezone
from json import loads
from logging import getLogger
import zmq

from . import common
from .evstore import initdb, stow, stowloc, stowpmod
from .zmsg import Bcast, Rept

log = getLogger("loctrkd/storage")


def runserver(conf: ConfigParser) -> None:
    stowevents = conf.getboolean("storage", "events", fallback=False)
    dbname = conf.get("storage", "dbfn")
    log.info('Using Sqlite3 database "%s"', dbname)
    initdb(dbname)
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
                        log.debug(
                            "%s IMEI %s from %s at %s %s: %s",
                            "I" if zmsg.is_incoming else "O",
                            zmsg.imei,
                            zmsg.peeraddr,
                            zmsg.pmod,
                            datetime.fromtimestamp(zmsg.when).astimezone(
                                tz=timezone.utc
                            ),
                            zmsg.packet.hex(),
                        )
                        if zmsg.imei is not None and zmsg.pmod is not None:
                            stowpmod(zmsg.imei, zmsg.pmod)
                        if stowevents:
                            stow(
                                is_incoming=zmsg.is_incoming,
                                peeraddr=str(zmsg.peeraddr),
                                when=zmsg.when,
                                imei=zmsg.imei,
                                proto=zmsg.proto,
                                packet=zmsg.packet,
                            )
                elif sk is zrep:
                    while True:
                        try:
                            rept = Rept(zrep.recv(zmq.NOBLOCK))
                        except zmq.Again:
                            break
                        data = loads(rept.payload)
                        log.debug("R IMEI %s %s", rept.imei, data)
                        if data.pop("type") == "location":
                            data["imei"] = rept.imei
                            stowloc(**data)

                else:
                    log.error("Event %s on unknown socket %s", fl, sk)
    except KeyboardInterrupt:
        zrep.close()
        zraw.close()
        zctx.destroy()  # type: ignore


if __name__.endswith("__main__"):
    runserver(common.init(log))
