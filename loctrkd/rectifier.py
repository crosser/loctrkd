""" Estimate coordinates from WIFI_POSITIONING and send back """

from configparser import ConfigParser
from datetime import datetime, timezone
from importlib import import_module
from logging import getLogger
from os import umask
from struct import pack
from typing import cast, List, Tuple
import zmq

from . import common
from .common import CoordReport, HintReport, StatusReport, Report
from .zmsg import Bcast, Rept, Resp, topic

log = getLogger("loctrkd/rectifier")


class QryModule:
    @staticmethod
    def init(conf: ConfigParser) -> None:
        ...

    @staticmethod
    def shut() -> None:
        ...

    @staticmethod
    def lookup(
        mcc: int,
        mnc: int,
        gsm_cells: List[Tuple[int, int, int]],
        wifi_aps: List[Tuple[str, int]],
    ) -> Tuple[float, float, float]:
        ...


def runserver(conf: ConfigParser) -> None:
    qry = cast(
        QryModule,
        import_module("." + conf.get("rectifier", "lookaside"), __package__),
    )
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
    oldmask = umask(0o117)
    zpub.bind(conf.get("rectifier", "publishurl"))
    umask(oldmask)

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
            rect: Report = msg.rectified()
            log.debug("rectified: %s", rect)
            if isinstance(rect, (CoordReport, StatusReport)):
                zpub.send(Rept(imei=zmsg.imei, payload=rect.json).packed)
            elif isinstance(rect, HintReport):
                try:
                    lat, lon, acc = qry.lookup(
                        rect.mcc,
                        rect.mnc,
                        rect.gsm_cells,
                        list((mac, strng) for _, mac, strng in rect.wifi_aps),
                    )
                    log.debug(
                        "Approximated lat=%s, lon=%s, acc=%s for %s",
                        lat,
                        lon,
                        acc,
                        rect,
                    )
                    if proto_needanswer.get(zmsg.proto, False):
                        resp = Resp(
                            imei=zmsg.imei,
                            when=zmsg.when,  # not the current time, but the original!
                            packet=msg.Out(latitude=lat, longitude=lon).packed,
                        )
                        log.debug("Sending reponse %s", resp)
                        zpush.send(resp.packed)
                    rept = CoordReport(
                        devtime=rect.devtime,
                        battery_percentage=rect.battery_percentage,
                        accuracy=acc,
                        altitude=None,
                        speed=None,
                        direction=None,
                        latitude=lat,
                        longitude=lon,
                    )
                    log.debug("Sending report %s", rept)
                    zpub.send(
                        Rept(
                            imei=zmsg.imei,
                            payload=rept.json,
                        ).packed
                    )
                except Exception as e:
                    log.exception(
                        "Lookup for %s rectified as %s resulted in %s",
                        msg,
                        rect,
                        e,
                    )

    except KeyboardInterrupt:
        zsub.close()
        zpub.close()
        zpush.close()
        zctx.destroy()  # type: ignore
        qry.shut()


if __name__.endswith("__main__"):
    runserver(common.init(log))
