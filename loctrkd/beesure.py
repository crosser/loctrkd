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

__all__ = (
    "Stream",
    "class_by_prefix",
    "enframe",
    "inline_response",
    "parse_message",
    "probe_buffer",
    "proto_by_name",
    "proto_name",
    "DecodeError",
    "Respond",
    "LK",
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


class MetaPkt(type):
    """
    For each class corresponding to a message, automatically create
    two nested classes `In` and `Out` that also inherit from their
    "nest". Class attribute `IN_KWARGS` defined in the "nest" is
    copied to the `In` nested class under the name `KWARGS`, and
    likewise, `OUT_KWARGS` of the nest class is copied as `KWARGS`
    to the nested class `Out`. In addition, method `encode` is
    defined in both classes equal to `in_encode()` and `out_encode()`
    respectively.
    """

    if TYPE_CHECKING:

        def __getattr__(self, name: str) -> Any:
            pass

        def __setattr__(self, name: str, value: Any) -> None:
            pass

    def __new__(
        cls: Type["MetaPkt"],
        name: str,
        bases: Tuple[type, ...],
        attrs: Dict[str, Any],
    ) -> "MetaPkt":
        newcls = super().__new__(cls, name, bases, attrs)
        newcls.In = super().__new__(
            cls,
            name + ".In",
            (newcls,) + bases,
            {
                "KWARGS": newcls.IN_KWARGS,
                "decode": newcls.in_decode,
                "encode": newcls.in_encode,
            },
        )
        newcls.Out = super().__new__(
            cls,
            name + ".Out",
            (newcls,) + bases,
            {
                "KWARGS": newcls.OUT_KWARGS,
                "decode": newcls.out_decode,
                "encode": newcls.out_encode,
            },
        )
        return newcls


class Respond(Enum):
    NON = 0  # Incoming, no response needed
    INL = 1  # Birirectional, use `inline_response()`
    EXT = 2  # Birirectional, use external responder


class BeeSurePkt(metaclass=MetaPkt):
    RESPOND = Respond.NON  # Do not send anything back by default
    PROTO: str
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
        assert not args or (len(args) == 4 and not kwargs)
        if args:  # guaranteed to be two arguments at this point
            self.vendor, self.imei, self.datalength, self.payload = args
            try:
                self.decode(*self.payload)
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

    def decode(self, *args: str) -> None:
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
        return self.PROTO

    @property
    def packed(self) -> bytes:
        buffer = self.encode().encode()
        return f"[LT*0000000000*{len(buffer):04X}*".encode() + buffer + b"]"


class UNKNOWN(BeeSurePkt):
    PROTO = "UNKNOWN"


class LK(BeeSurePkt):
    PROTO = "LK"
    RESPOND = Respond.INL

    def in_decode(self, *args: str) -> None:
        numargs = len(args)
        if numargs > 1:
            self.step = args[1]
        if numargs > 2:
            self.tumbling_number = args[2]
        if numargs > 3:
            self.battery_percentage = args[3]

    def in_encode(self) -> str:
        return "LK"


class CONFIG(BeeSurePkt):
    PROTO = "CONFIG"


class ICCID(BeeSurePkt):
    PROTO = "ICCID"


class UD(BeeSurePkt):
    PROTO = "UD"

    def in_decode(self, *args: str) -> None:
        (
            _,
            self.date,
            self.time,
            self.gps_valid,
            self.lat,
            self.nors,
            self.lon,
            self.eorw,
            self.speed,
            self.direction,
            self.altitude,
            self.num_of_sats,
            self.gsm_strength_percentage,
            self.battery_percentage,
            self.pedometer,
            self.tubmling_times,
            self.device_status,
        ) = args[:17]
        rest_args = args[17:]
        self.base_stations_number = int(rest_args[0])
        self.base_stations = rest_args[1 : 4 + 3 * self.base_stations_number]
        rest_args = rest_args[3 + 3 * self.base_stations_number + 1 :]
        self.wifi_ap_number = int(rest_args[0])
        self.wifi_ap = rest_args[1 : self.wifi_ap_number]
        # rest_args = rest_args[self_wifi_ap_number+1:]
        self.positioning_accuracy = rest_args[-1]


class UD2(BeeSurePkt):
    PROTO = "UD2"


class TKQ(BeeSurePkt):
    PROTO = "TKQ"
    RESPOND = Respond.INL


class TKQ2(BeeSurePkt):
    PROTO = "TKQ2"
    RESPOND = Respond.INL


class AL(BeeSurePkt):
    PROTO = "AL"
    RESPOND = Respond.INL


# Build dicts protocol number -> class and class name -> protocol number
CLASSES = {}
PROTOS = {}
if True:  # just to indent the code, sorry!
    for cls in [
        cls
        for name, cls in globals().items()
        if isclass(cls)
        and issubclass(cls, BeeSurePkt)
        and not name.startswith("_")
    ]:
        if hasattr(cls, "PROTO"):
            CLASSES[cls.PROTO] = cls
            PROTOS[cls.__name__] = cls.PROTO


def class_by_prefix(
    prefix: str,
) -> Union[Type[BeeSurePkt], List[Tuple[str, str]]]:
    lst = [
        (name, proto)
        for name, proto in PROTOS.items()
        if name.upper().startswith(prefix.upper())
    ]
    if len(lst) != 1:
        return lst
    _, proto = lst[0]
    return CLASSES[proto]


def proto_name(obj: Union[MetaPkt, BeeSurePkt]) -> str:
    return PROTO_PREFIX + (
        obj.__class__.__name__ if isinstance(obj, BeeSurePkt) else obj.__name__
    )


def proto_by_name(name: str) -> str:
    return PROTO_PREFIX + PROTOS.get(name, "UNKNOWN")


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
    payload = packet[20:-1].decode().split(",")
    proto = payload[0] if len(payload) > 0 else ""
    if proto not in CLASSES:
        cause: Union[DecodeError, ValueError, IndexError] = ValueError(
            f"Proto {proto} is unknown"
        )
    else:
        try:
            if is_incoming:
                return CLASSES[proto].In(vendor, imei, datalength, payload)
            else:
                return CLASSES[proto].Out(vendor, imei, datalength, payload)
        except (DecodeError, ValueError, IndexError) as e:
            cause = e
    if is_incoming:
        retobj = UNKNOWN.In(vendor, imei, datalength, payload)
    else:
        retobj = UNKNOWN.Out(vendor, imei, datalength, payload)
    retobj.PROTO = proto  # Override class attr with object attr
    retobj.cause = cause
    return retobj
