""" For when responding to the terminal is not trivial """

from datetime import datetime, timezone
from logging import getLogger
from struct import pack
import zmq

from . import common
from .gps303proto import parse_message, proto_by_name
from .zmsg import Bcast, Resp

log = getLogger("gps303/termconfig")


def runserver(conf):
    zctx = zmq.Context()
    zsub = zctx.socket(zmq.SUB)
    zsub.connect(conf.get("collector", "publishurl"))
    for protoname in (
        "SUPERVISION",
        "STATUS",
        "RESET",
        "WHITELIST_TOTAL",
        "PROHIBIT_LBS",
        "SETUP",
        "POSITION_UPLOAD_INTERVAL",
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
            # TODO get data from the config
            resp = Resp(imei=zmsg.imei, packet=msg.response())
            log.debug("Response: %s", resp)
            zpush.send(resp.packed)

    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
