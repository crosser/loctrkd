""" Estimate coordinates from WIFI_POSITIONING and send back """

from datetime import datetime, timezone
from logging import getLogger
from os import umask
from struct import pack
import zmq

from . import common
from .gps303proto import parse_message, proto_by_name, WIFI_POSITIONING
from .opencellid import qry_cell
from .zmsg import Bcast, LocEvt, Resp

log = getLogger("gps303/lookaside")


def runserver(conf):
    zctx = zmq.Context()
    zpub = zctx.socket(zmq.PUB)
    oldmask = umask(0o117)
    zpub.bind(conf.get("lookaside", "publishurl"))
    umask(oldmask)
    zsub = zctx.socket(zmq.SUB)
    zsub.connect(conf.get("collector", "publishurl"))
    for protoname in (
        "GPS_POSITIONING",
        "WIFI_POSITIONING",
    ):
        topic = pack("B", proto_by_name(protoname))
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
            if isinstance(msg, WIFI_POSITIONING):
                is_gps = False
                lat, lon = qry_cell(
                    conf["opencellid"]["dbfn"], msg.mcc, msg.gsm_cells
                )
                resp = Resp(
                    imei=zmsg.imei, packet=msg.Out(lat=lat, lon=lon).packed
                )
                log.debug("Response for lat=%s, lon=%s: %s", lat, lon, resp)
                zpush.send(resp.packed)
            else:
                is_gps = True
                lat = msg.latitude
                lon = msg.longitude
            zpub.send(
                LocEvt(
                    imei=zmsg.imei,
                    devtime=msg.devtime,
                    is_gps=is_gps,
                    lat=lat,
                    lon=lon,
                ).packed
            )

    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
