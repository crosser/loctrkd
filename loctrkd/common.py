""" Common housekeeping for all daemons """

from configparser import ConfigParser
from importlib import import_module
from getopt import getopt
from json import dumps
from logging import Formatter, getLogger, Logger, StreamHandler, DEBUG, INFO
from logging.handlers import SysLogHandler
from pkg_resources import get_distribution, DistributionNotFound
from sys import argv, stderr, stdout
from typing import Any, cast, Dict, List, Optional, Tuple, Union
from types import SimpleNamespace

from .protomodule import ProtoModule

CONF = "/etc/loctrkd.conf"
pmods: List[ProtoModule] = []

try:
    version = get_distribution("loctrkd").version
except DistributionNotFound:
    version = "<local>"


def init_protocols(conf: ConfigParser) -> None:
    global pmods
    pmods = [
        cast(ProtoModule, import_module("." + modnm, __package__))
        for modnm in conf.get("common", "protocols").split(",")
    ]


def init(
    log: Logger, opts: Optional[List[Tuple[str, str]]] = None
) -> ConfigParser:
    if opts is None:
        opts, _ = getopt(argv[1:], "c:d")
    dopts = dict(opts)
    conf = ConfigParser()
    conf.read(dopts["-c"] if "-c" in dopts else CONF)
    log.setLevel(DEBUG if "-d" in dopts else INFO)
    if stdout.isatty():
        fhdl = StreamHandler(stderr)
        fhdl.setFormatter(
            Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        log.addHandler(fhdl)
        log.debug("%s starting with options: %s", version, dopts)
    else:
        lhdl = SysLogHandler(address="/dev/log")
        lhdl.setFormatter(
            Formatter("%(name)s[%(process)d]: %(levelname)s - %(message)s")
        )
        log.addHandler(lhdl)
        log.info("%s starting with options: %s", version, dopts)
    init_protocols(conf)
    return conf


def probe_pmod(segment: bytes) -> Optional[ProtoModule]:
    for pmod in pmods:
        if pmod.probe_buffer(segment):
            return pmod
    return None


def pmod_for_proto(proto: str) -> Optional[ProtoModule]:
    for pmod in pmods:
        if pmod.proto_handled(proto):
            return pmod
    return None


def parse_message(proto: str, packet: bytes, is_incoming: bool = True) -> Any:
    pmod = pmod_for_proto(proto)
    return pmod.parse_message(packet, is_incoming) if pmod else None


def exposed_protos() -> List[Tuple[str, bool]]:
    return [item for pmod in pmods for item in pmod.exposed_protos()]


class Report(SimpleNamespace):
    TYPE: str

    @property
    def json(self) -> str:
        self.type = self.TYPE
        return dumps(self.__dict__)


class CoordReport(Report):
    TYPE = "location"

    def __init__(
        self,
        *,
        devtime: str,
        battery_percentage: int,
        accuracy: float,
        altitude: float,
        speed: float,
        direction: float,
        latitude: float,
        longitude: float
    ) -> None:
        super().__init__(
            devtime=devtime,
            battery_percentage=battery_percentage,
            accuracy=accuracy,
            altitude=altitude,
            speed=speed,
            direction=direction,
            latitude=latitude,
            longitude=longitude,
        )


class HintReport(Report):
    TYPE = "approximate_location"

    def __init__(
        self,
        *,
        devtime: str,
        battery_percentage: int,
        mcc: int,
        mnc: int,
        gsm_cells: List[Tuple[int, int, int]],
        wifi_aps: List[Tuple[str, str, int]]
    ) -> None:
        super().__init__(
            devtime=devtime,
            battery_percentage=battery_percentage,
            mcc=mcc,
            mnc=mnc,
            gsm_cells=gsm_cells,
            wifi_aps=wifi_aps,
        )


class StatusReport(Report):
    TYPE = "status"

    def __init__(self, *, battery_percentage: int) -> None:
        super().__init__(battery_percentage=battery_percentage)
