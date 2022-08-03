"""
Implementation of the protocol "beesure" used by some watch-trackers
https://www.4p-touch.com/beesure-gps-setracker-server-protocol.html
"""

from datetime import datetime, timezone
from enum import Enum
from inspect import isclass
import re
from struct import error, pack, unpack
from time import time
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    TYPE_CHECKING,
    Union,
)
from types import SimpleNamespace

from .protomodule import ProtoClass
from .common import (
    CoordReport,
    HintReport,
    StatusReport,
    Report,
)

__all__ = (
    "Stream",
    "class_by_prefix",
    "enframe",
    "exposed_protos",
    "inline_response",
    "proto_handled",
    "parse_message",
    "probe_buffer",
    "DecodeError",
    "Respond",
)

PROTO_PREFIX = "BS:"

### Deframer ###

MAXBUFFER: int = 65557  # Theoretical max buffer 65536 + 21
RE = re.compile(b"\[(\w\w)\*(\d{10})\*([0-9a-fA-F]{4})\*")


def _framestart(buffer: bytes) -> Tuple[int, str, str, int]:
    """
    Find the start of the frame in the buffer.
    If found, return (offset, vendorId, imei, datalen) tuple.
    If not found, set -1 as the value of `offset`
    """
    mo = RE.search(buffer)
    return (
        (
            mo.start(),
            mo.group(1).decode(),
            mo.group(2).decode(),
            int(mo.group(3), 16),
        )
        if mo
        else (-1, "", "", 0)
    )


class Stream:
    def __init__(self) -> None:
        self.buffer = b""
        self.imei: Optional[str] = None
        self.datalen: int = 0

    def recv(self, segment: bytes) -> List[Union[bytes, str]]:
        """
        Process next segment of the stream. Return successfully deframed
        packets as `bytes` and error messages as `str`.
        """
        when = time()
        self.buffer += segment
        if len(self.buffer) > MAXBUFFER:
            # We are receiving junk. Let's drop it or we run out of memory.
            self.buffer = b""
            return [f"More than {MAXBUFFER} unparseable data, dropping"]
        msgs: List[Union[bytes, str]] = []
        while True:
            if not self.datalen:  # we have not seen packet start yet
                toskip, _, imei, datalen = _framestart(self.buffer)
                if toskip < 0:  # No frames, continue reading
                    break
                if toskip > 0:  # Should not happen, report
                    msgs.append(
                        f"Skipping {toskip} bytes of undecodable data"
                        f' "{self.buffer[:toskip][:64]=!r}"'
                    )
                    self.buffer = self.buffer[toskip:]
                    # From this point, buffer starts with a packet header
                if self.imei is None:
                    self.imei = imei
                if self.imei != imei:
                    msgs.append(
                        f"Packet's imei {imei} mismatches"
                        f" previous value {self.imei}, old value kept"
                    )
                self.datalen = datalen
            if len(self.buffer) < self.datalen + 21:  # Incomplete packet
                break
            # At least one complete packet is present in the buffer
            if chr(self.buffer[self.datalen + 20]) == "]":
                msgs.append(self.buffer[: self.datalen + 21])
            else:
                msgs.append(
                    f"Packet does not end with ']'"
                    f" at {self.datalen+20}: {self.buffer=!r}"
                )
            self.buffer = self.buffer[self.datalen + 21 :]
            self.datalen = 0
        return msgs

    def close(self) -> bytes:
        ret = self.buffer
        self.buffer = b""
        self.imei = None
        self.datalen = 0
        return ret


def enframe(buffer: bytes, imei: Optional[str] = None) -> bytes:
    assert imei is not None and len(imei) == 10
    off, vid, _, dlen = _framestart(buffer)
    assert off == 0
    return f"[{vid:2s}*{imei:10s}*{dlen:04X}*".encode() + buffer[20:]


### Parser/Constructor ###


class classproperty:
    def __init__(self, f: Callable[[Any], str]) -> None:
        self.f = f

    def __get__(self, obj: Any, owner: Any) -> str:
        return self.f(owner)


class DecodeError(Exception):
    def __init__(self, e: Exception, **kwargs: Any) -> None:
        super().__init__(e)
        for k, v in kwargs.items():
            setattr(self, k, v)


def maybe(typ: type) -> Callable[[Any], Any]:
    return lambda x: None if x is None else typ(x)


def intx(x: Union[str, int]) -> int:
    if isinstance(x, str):
        x = int(x, 0)
    return x


def boolx(x: Union[str, bool]) -> bool:
    if isinstance(x, str):
        if x.upper() in ("ON", "TRUE", "1"):
            return True
        if x.upper() in ("OFF", "FALSE", "0"):
            return False
        raise ValueError(str(x) + " could not be parsed as a Boolean")
    return x


def l3str(x: Union[str, List[str]]) -> List[str]:
    if isinstance(x, str):
        lx = x.split(",")
    else:
        lx = x
    if len(lx) != 3 or not all(isinstance(el, str) for el in x):
        raise ValueError(str(lx) + " is not a list of three strings")
    return lx


def pblist(x: Union[str, List[Tuple[str, str]]]) -> List[Tuple[str, str]]:
    if isinstance(x, str):

        def splitpair(s: str) -> Tuple[str, str]:
            a, b = s.split(":")
            return a, b

        lx = [splitpair(el) for el in x.split(",")]
    else:
        lx = x
    if len(lx) > 5:
        raise ValueError(str(lx) + " has too many elements (max 5)")
    return lx


class Respond(Enum):
    NON = 0  # Incoming, no response needed
    INL = 1  # Birirectional, use `inline_response()`
    EXT = 2  # Birirectional, use external responder


class BeeSurePkt(ProtoClass):
    BINARY = False
    RESPOND = Respond.NON  # Do not send anything back by default
    IN_KWARGS: Tuple[Tuple[str, Callable[[Any], Any], Any], ...] = ()
    OUT_KWARGS: Tuple[Tuple[str, Callable[[Any], Any], Any], ...] = ()
    KWARGS: Tuple[Tuple[str, Callable[[Any], Any], Any], ...] = ()
    In: Type["BeeSurePkt"]
    Out: Type["BeeSurePkt"]

    if TYPE_CHECKING:

        def __getattr__(self, name: str) -> Any:
            pass

        def __setattr__(self, name: str, value: Any) -> None:
            pass

    def __init__(self, *args: Any, **kwargs: Any):
        """
        Construct the object _either_ from (length, payload),
        _or_ from the values of individual fields
        """
        self.payload: Union[List[str], bytes]
        assert not args or (len(args) == 4 and not kwargs)
        if args:  # guaranteed to be two arguments at this point
            self.vendor, self.imei, self.datalength, self.payload = args
            try:
                if isinstance(self.payload, list):
                    self.decode(*self.payload)
                else:
                    self.decode(self.payload)
            except error as e:
                raise DecodeError(e, obj=self)
        else:
            for kw, typ, dfl in self.KWARGS:
                setattr(self, kw, typ(kwargs.pop(kw, dfl)))
            if kwargs:
                raise ValueError(
                    self.__class__.__name__ + " stray kwargs " + str(kwargs)
                )

    def __repr__(self) -> str:
        return "{}({})".format(
            self.__class__.__name__,
            ", ".join(
                "{}={}".format(
                    k,
                    'bytes.fromhex("{}")'.format(v.hex())
                    if isinstance(v, bytes)
                    else v.__repr__(),
                )
                for k, v in self.__dict__.items()
                if not k.startswith("_")
            ),
        )

    def decode(self, *args: Any) -> None:
        ...

    def in_decode(self, *args: str) -> None:
        # Overridden in subclasses, otherwise do not decode payload
        return

    def out_decode(self, *args: str) -> None:
        # Overridden in subclasses, otherwise do not decode payload
        return

    def encode(self) -> str:
        ...

    def in_encode(self) -> str:
        # Necessary to emulate terminal, which is not implemented
        raise NotImplementedError(
            self.__class__.__name__ + ".encode() not implemented"
        )

    def out_encode(self) -> str:
        # Overridden in subclasses, otherwise command verb only
        return ""

    @classproperty
    def PROTO(cls: "BeeSurePkt") -> str:
        """Name of the class without possible .In / .Out suffix"""
        proto: str
        try:
            proto, _ = cls.__name__.split(".")
        except ValueError:
            proto = cls.__name__
        return proto

    @classmethod
    def proto_name(cls) -> str:
        """Name of the command as used externally"""
        return PROTO_PREFIX + cls.PROTO[:16]

    @property
    def packed(self) -> bytes:
        data = self.encode()
        payload = self.PROTO + "," + data if data else self.PROTO
        return f"[LT*0000000000*{len(payload):04X}*{payload}]".encode()


class UNKNOWN(BeeSurePkt):
    pass


class _LOC_DATA(BeeSurePkt):
    def in_decode(self, *args: str) -> None:
        p = SimpleNamespace()
        _id = lambda x: x
        for (obj, attr, func), val in zip(
            (
                (p, "date", _id),
                (p, "time", _id),
                (self, "gps_valid", lambda x: x == "A"),
                (p, "lat", float),
                (p, "nors", lambda x: 1 if x == "N" else -1),
                (p, "lon", float),
                (p, "eorw", lambda x: 1 if x == "E" else -1),
                (self, "speed", float),
                (self, "direction", float),
                (self, "altitude", float),
                (self, "num_of_sats", int),
                (self, "gsm_strength_percentage", int),
                (self, "battery_percentage", int),
                (self, "pedometer", int),
                (self, "tubmling_times", int),
                (self, "device_status", lambda x: int(x, 16)),
                (self, "gsm_cells_number", int),
                (self, "connect_base_station_number", int),
                (self, "mcc", int),
                (self, "mnc", int),
            ),
            args[:20],
        ):
            setattr(obj, attr, func(val))  # type: ignore
        rest_args = args[20:]
        # (area_id, cell_id, strength)*
        self.gsm_cells: List[Tuple[int, int, int]] = [
            tuple(int(el) for el in rest_args[i * 3 : 3 + i * 3])  # type: ignore
            for i in range(self.gsm_cells_number)
        ]
        rest_args = rest_args[3 * self.gsm_cells_number :]
        self.wifi_aps_number = int(rest_args[0])
        # (SSID, MAC, strength)*
        self.wifi_aps = [
            (
                rest_args[1 + i * 3],
                rest_args[2 + i * 3],
                int(rest_args[3 + i * 3]),
            )
            for i in range(self.wifi_aps_number)
        ]
        rest_args = rest_args[1 + 3 * self.wifi_aps_number :]
        self.positioning_accuracy = float(rest_args[0])
        self.devtime = (
            datetime.strptime(
                p.date + p.time,
                "%d%m%y%H%M%S",
            )
            # .replace(tzinfo=timezone.utc)
            # .astimezone(tz=timezone.utc)
        )
        self.latitude = p.lat * p.nors
        self.longitude = p.lon * p.eorw

    def rectified(self) -> Report:
        if self.gps_valid:
            return CoordReport(
                devtime=str(self.devtime),
                battery_percentage=self.battery_percentage,
                accuracy=self.positioning_accuracy,
                altitude=self.altitude,
                speed=self.speed,
                direction=self.direction,
                latitude=self.latitude,
                longitude=self.longitude,
            )
        else:
            return HintReport(
                devtime=str(self.devtime),
                battery_percentage=self.battery_percentage,
                mcc=self.mcc,
                mnc=self.mnc,
                gsm_cells=self.gsm_cells,
                wifi_aps=self.wifi_aps,
            )


class AL(_LOC_DATA):
    RESPOND = Respond.INL


class CONFIG(BeeSurePkt):
    pass


class CR(BeeSurePkt):
    pass


class FLOWER(BeeSurePkt):
    OUT_KWARGS = (("number", int, 1),)

    def out_encode(self) -> str:
        self.number: int
        return str(self.number)


class ICCID(BeeSurePkt):
    pass


class LK(BeeSurePkt):
    RESPOND = Respond.INL

    def in_decode(self, *args: str) -> None:
        numargs = len(args)
        if numargs > 0:
            self.step = args[0]
        if numargs > 1:
            self.tumbling_number = args[1]
        if numargs > 2:
            self.battery_percentage = args[2]

    def in_encode(self) -> str:
        return "LK"


class MESSAGE(BeeSurePkt):
    OUT_KWARGS = (("message", str, ""),)

    def out_encode(self) -> str:
        return str(self.message.encode("utf_16_be").hex())


class _PHB(BeeSurePkt):
    OUT_KWARGS: Tuple[Tuple[str, Callable[[Any], Any], Any], ...] = (
        ("entries", pblist, []),
    )

    def out_encode(self) -> str:
        self.entries: List[Tuple[str, str]]
        return ",".join(
            [
                ",".join((num, name.encode("utf_16_be").hex()))
                for name, num in self.entries
            ]
        )


class PHB(_PHB):
    pass


class PHB2(_PHB):
    pass


class POWEROFF(BeeSurePkt):
    pass


class RESET(BeeSurePkt):
    pass


class SOS(BeeSurePkt):
    OUT_KWARGS = (("phonenumbers", l3str, ["", "", ""]),)

    def out_encode(self) -> str:
        self.phonenumbers: List[str]
        return ",".join(self.phonenumbers)


class _SET_PHONE(BeeSurePkt):
    OUT_KWARGS = (("phonenumber", str, ""),)

    def out_encode(self) -> str:
        self.phonenumber: str
        return self.phonenumber


class SOS1(_SET_PHONE):
    pass


class SOS2(_SET_PHONE):
    pass


class SOS3(_SET_PHONE):
    pass


class TK(BeeSurePkt):
    BINARY = True
    RESPOND = Respond.INL

    def in_decode(self, *args: Any) -> None:
        assert len(args) == 1 and isinstance(args[0], bytes)
        self.amr_data = (
            args[0]
            .replace(b"}*", b"*")
            .replace(b"},", b",")
            .replace(b"}[", b"[")
            .replace(b"}]", b"]")
            .replace(b"}}", b"}")
        )

    def out_encode(self) -> str:
        return "1"  # 0 - receive failure, 1 - receive success


class TKQ(BeeSurePkt):
    RESPOND = Respond.INL


class TKQ2(BeeSurePkt):
    RESPOND = Respond.INL


class UD(_LOC_DATA):
    pass


class UD2(_LOC_DATA):
    pass


# Build dicts protocol number -> class and class name -> protocol number
CLASSES = {}
if True:  # just to indent the code, sorry!
    for cls in [
        cls
        for name, cls in globals().items()
        if isclass(cls)
        and issubclass(cls, BeeSurePkt)
        and not name.startswith("_")
    ]:
        CLASSES[cls.__name__] = cls


def class_by_prefix(
    prefix: str,
) -> Union[Type[BeeSurePkt], List[str]]:
    if prefix.startswith(PROTO_PREFIX):
        pname = prefix[len(PROTO_PREFIX) :].upper()
    else:
        raise KeyError(pname)
    lst = [name for name in CLASSES.keys() if name.upper().startswith(pname)]
    for proto in lst:
        if len(lst) == 1:  # unique prefix match
            return CLASSES[proto]
        if proto == pname:  # exact match
            return CLASSES[proto]
    return lst


def proto_handled(proto: str) -> bool:
    return proto.startswith(PROTO_PREFIX)


def proto_of_message(packet: bytes) -> str:
    return PROTO_PREFIX + packet[20:-1].split(b",")[0].decode()


def imei_from_packet(packet: bytes) -> Optional[str]:
    toskip, _, imei, _ = _framestart(packet)
    if toskip == 0 and imei != "":
        return imei
    return None


def is_goodbye_packet(packet: bytes) -> bool:
    return False


def inline_response(packet: bytes) -> Optional[bytes]:
    proto = packet[20:-1].split(b",")[0].decode()
    if proto in CLASSES:
        cls = CLASSES[proto]
        if cls.RESPOND is Respond.INL:
            return cls.Out().packed
    return None


def probe_buffer(buffer: bytes) -> bool:
    return bool(RE.search(buffer))


def parse_message(packet: bytes, is_incoming: bool = True) -> BeeSurePkt:
    """From a packet (without framing bytes) derive the XXX.In object"""
    toskip, vendor, imei, datalength = _framestart(packet)
    bsplits = packet[20:-1].split(b",", 1)
    try:
        proto = bsplits[0].decode("ascii")
    except UnicodeDecodeError:
        proto = str(bsplits[0])
    if len(bsplits) == 2:
        rest = bsplits[1]
    else:
        rest = b""
    if proto in CLASSES:
        cls = CLASSES[proto].In if is_incoming else CLASSES[proto].Out
        payload = (
            # Some people encode their SSIDs in non-utf8
            rest
            if cls.BINARY
            else rest.decode("Windows-1252").split(",")
        )
        try:
            return cls(vendor, imei, datalength, payload)
        except (DecodeError, ValueError, IndexError) as e:
            cause: Union[DecodeError, ValueError, IndexError] = e
    else:
        payload = rest
        cause = ValueError(f"Proto {proto} is unknown")
    if is_incoming:
        retobj = UNKNOWN.In(vendor, imei, datalength, payload)
    else:
        retobj = UNKNOWN.Out(vendor, imei, datalength, payload)
    retobj.proto = proto  # Override class attr with object attr
    retobj.cause = cause
    return retobj


def exposed_protos() -> List[Tuple[str, bool]]:
    return [
        (cls.proto_name(), False)
        for cls in CLASSES.values()
        if hasattr(cls, "rectified")
    ]
