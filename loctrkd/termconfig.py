""" For when responding to the terminal is not trivial """

from configparser import ConfigParser, SectionProxy
from datetime import datetime, timezone
from logging import getLogger
from struct import pack
from typing import Any, Dict, List, Union
import zmq

from . import common
from .zx303proto import *
from .zx303proto import STATUS, SETUP, POSITION_UPLOAD_INTERVAL
from .zmsg import Bcast, Resp, topic

log = getLogger("loctrkd/termconfig")


def normconf(section: SectionProxy) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, val in section.items():
        vals = val.split("\n")
        if len(vals) > 1 and vals[0] == "":
            vals = vals[1:]
        lst: List[Union[str, int]] = []
        for el in vals:
            try:
                lst.append(int(el, 0))
            except ValueError:
                if el[0] == '"' and el[-1] == '"':
                    el = el.strip('"').rstrip('"')
                lst.append(el)
        if not (
            all([isinstance(x, int) for x in lst])
            or all([isinstance(x, str) for x in lst])
        ):
            raise ValueError(
                "Values of %s - %s are of different type", key, vals
            )
        if len(lst) == 1:
            result[key] = lst[0]
        else:
            result[key] = lst
    return result


def runserver(conf: ConfigParser) -> None:
    # Is this https://github.com/zeromq/pyzmq/issues/1627 still not fixed?!
    zctx = zmq.Context()  # type: ignore
    zsub = zctx.socket(zmq.SUB)  # type: ignore
    zsub.connect(conf.get("collector", "publishurl"))
    for proto in (
        STATUS.proto_name(),
        SETUP.proto_name(),
        POSITION_UPLOAD_INTERVAL.proto_name(),
    ):
        zsub.setsockopt(zmq.SUBSCRIBE, topic(proto))
    zpush = zctx.socket(zmq.PUSH)  # type: ignore
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
            if msg.RESPOND is not Respond.EXT:
                log.error(
                    "%s does not expect externally provided response", msg
                )
            if zmsg.imei is not None and conf.has_section(zmsg.imei):
                termconfig = normconf(conf[zmsg.imei])
            elif conf.has_section("termconfig"):
                termconfig = normconf(conf["termconfig"])
            else:
                termconfig = {}
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
            resp = Resp(
                imei=zmsg.imei, when=zmsg.when, packet=msg.Out(**kwargs).packed
            )
            log.debug("Response: %s", resp)
            zpush.send(resp.packed)

    except KeyboardInterrupt:
        zsub.close()
        zpush.close()
        zctx.destroy()  # type: ignore


if __name__.endswith("__main__"):
    runserver(common.init(log))
