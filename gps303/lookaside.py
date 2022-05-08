""" Estimate coordinates from WIFI_POSITIONING and send back """

from datetime import datetime, timezone
from logging import getLogger
from os import umask
from struct import pack
import zmq

from . import common
from .gps303proto import parse_message, proto_by_name, WIFI_POSITIONING
from .opencellid import qry_cell
from .zmsg import Bcast, Resp

log = getLogger("gps303/lookaside")


def runserver(conf):
    zctx = zmq.Context()
    zsub = zctx.socket(zmq.SUB)
    zsub.connect(conf.get("collector", "publishurl"))
    topic = pack("B", proto_by_name("WIFI_POSITIONING"))
    zsub.setsockopt(zmq.SUBSCRIBE, topic)
    zpush = zctx.socket(zmq.PUSH)
    zpush.connect(conf.get("collector", "listenurl"))

    try:
        while True:
            zmsg = Bcast(zsub.recv())
            msg = parse_message(zmsg.packet)
            log.debug(
                "IMEI %s from %s at %s: %s",
                zmsg.imei,
                zmsg.peeraddr,
                datetime.fromtimestamp(zmsg.when).astimezone(tz=timezone.utc),
                msg,
            )
            if not isinstance(msg, WIFI_POSITIONING):
                log.error(
                    "IMEI %s from %s at %s: %s",
                    zmsg.imei,
                    zmsg.peeraddr,
                    datetime.fromtimestamp(zmsg.when).astimezone(
                        tz=timezone.utc
                    ),
                    msg,
                )
                continue
            lat, lon = qry_cell(
                conf["opencellid"]["dbfn"], msg.mcc, msg.gsm_cells
            )
            resp = Resp(imei=zmsg.imei, packet=msg.Out(lat=lat, lon=lon).packed)
            log.debug("Response for lat=%s, lon=%s: %s", lat, lon, resp)
            zpush.send(resp.packed)

    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
