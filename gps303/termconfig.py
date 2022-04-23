""" For when responding to the terminal is not trivial """

from datetime import datetime, timezone
from logging import getLogger
from struct import pack
import zmq

from . import common
from .gps303proto import *
from .zmsg import Bcast, Resp

log = getLogger("gps303/termconfig")


def runserver(conf):
    termconfig = common.normconf(conf["termconfig"])
    zctx = zmq.Context()
    zsub = zctx.socket(zmq.SUB)
    zsub.connect(conf.get("collector", "publishurl"))
    for protoname in (
        "STATUS",
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
            if msg.DIR is not Dir.EXT:
                log.error(
                    "%s does not expect externally provided response", msg
                )
            kwargs = {}
            if isinstance(msg, STATUS):
                kwargs = {
                    "upload_interval": termconfig.get(
                        "statusintervalminutes", 25
                    )
                }
            elif isinstance(msg, SETUP):
                for key in (
                    "uploadintervalseconds",
                    "binaryswitch",
                    "alarms",
                    "dndtimeswitch",
                    "dndtimes",
                    "gpstimeswitch",
                    "gpstimestart",
                    "gpstimestop",
                    "phonenumbers",
                ):
                    if key in termconfig:
                        kwargs[key] = termconfig[key]
            resp = Resp(imei=zmsg.imei, packet=msg.response(**kwargs))
            log.debug("Response: %s", resp)
            zpush.send(resp.packed)

    except KeyboardInterrupt:
        pass


if __name__.endswith("__main__"):
    runserver(common.init(log))
