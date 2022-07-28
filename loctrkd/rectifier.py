""" Estimate coordinates from WIFI_POSITIONING and send back """

from configparser import ConfigParser
from datetime import datetime, timezone
from importlib import import_module
from logging import getLogger
from os import umask
from struct import pack
import zmq

from . import common
from .zmsg import Bcast, Report, Resp, topic

log = getLogger("loctrkd/rectifier")


def runserver(conf: ConfigParser) -> None:
    qry = import_module("." + conf.get("rectifier", "lookaside"), __package__)
    qry.init(conf)
    proto_needanswer = dict(common.exposed_protos())
    # Is this https://github.com/zeromq/pyzmq/issues/1627 still not fixed?!
    zctx = zmq.Context()  # type: ignore
    zsub = zctx.socket(zmq.SUB)  # type: ignore
    zsub.connect(conf.get("collector", "publishurl"))
    for proto in proto_needanswer.keys():
        zsub.setsockopt(zmq.SUBSCRIBE, topic(proto))
    zpush = zctx.socket(zmq.PUSH)  # type: ignore
    zpush.connect(conf.get("collector", "listenurl"))
    zpub = zctx.socket(zmq.PUB)  # type: ignore
    zpub.connect(conf.get("rectifier", "publishurl"))

    try:
        while True:
            zmsg = Bcast(zsub.recv())
            msg = common.parse_message(
                zmsg.proto, zmsg.packet, is_incoming=zmsg.is_incoming
            )
            log.debug(
                "IMEI %s from %s at %s: %s",
                zmsg.imei,
                zmsg.peeraddr,
                datetime.fromtimestamp(zmsg.when).astimezone(tz=timezone.utc),
                msg,
            )
            rect = msg.rectified()
            log.debug("rectified: %s", rect)
            if rect.type == "approximate_location":
                try:
                    lat, lon = qry.lookup(
                        rect.mcc, rect.mnc, rect.base_stations, rect.wifi_aps
                    )
                    resp = Resp(
                        imei=zmsg.imei,
                        when=zmsg.when,  # not the current time, but the original!
                        packet=msg.Out(latitude=lat, longitude=lon).packed,
                    )
                    log.debug(
                        "Response for lat=%s, lon=%s: %s", lat, lon, resp
                    )
                    zpush.send(resp.packed)
                except Exception as e:
                    log.warning("Lookup for %s resulted in %s", msg, e)

    except KeyboardInterrupt:
        zsub.close()
        zpub.close()
        zpush.close()
        zctx.destroy()  # type: ignore
        qry.shut()


if __name__.endswith("__main__"):
    runserver(common.init(log))
