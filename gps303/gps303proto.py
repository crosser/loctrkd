"""
Implementation of the protocol used by zx303 "ZhongXun Topin Locator"
GPS+GPRS module. Description lifted from this repository:
https://github.com/tobadia/petGPS/tree/master/resources

Forewarnings:
1. There is no security whatsoever. If you know the module's IMEI,
   you can feed fake data to the server, including fake location.
2. Ad-hoc choice of framing of messages (that are transferred over
   the TCP stream) makes it vulnerable to coincidental appearance
   of framing bytes in the middle of the message. Most of the time
   the server will receive one message in one TCP segment (i.e. in
   one `recv()` operation, but relying on that would break things
   if the path has lower MTU than the size of a message.
"""

from datetime import datetime, timezone
from enum import Enum
from inspect import isclass
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
    "GPS303Conn",
    "StreamError",
    "class_by_prefix",
    "inline_response",
    "parse_message",
    "proto_by_name",
    "DecodeError",
    "Respond",
    "GPS303Pkt",
    "UNKNOWN",
    "LOGIN",
    "SUPERVISION",
    "HEARTBEAT",
    "GPS_POSITIONING",
    "GPS_OFFLINE_POSITIONING",
    "STATUS",
    "HIBERNATION",
    "RESET",
    "WHITELIST_TOTAL",
    "WIFI_OFFLINE_POSITIONING",
    "TIME",
    "PROHIBIT_LBS",
    "GPS_LBS_SWITCH_TIMES",
    "REMOTE_MONITOR_PHONE",
    "SOS_PHONE",
    "DAD_PHONE",
    "MOM_PHONE",
    "STOP_UPLOAD",
    "GPS_OFF_PERIOD",
    "DND_PERIOD",
    "RESTART_SHUTDOWN",
    "DEVICE",
    "ALARM_CLOCK",
    "STOP_ALARM",
    "SETUP",
    "SYNCHRONOUS_WHITELIST",
    "RESTORE_PASSWORD",
    "WIFI_POSITIONING",
    "MANUAL_POSITIONING",
    "BATTERY_CHARGE",
    "CHARGER_CONNECTED",
    "CHARGER_DISCONNECTED",
    "VIBRATION_RECEIVED",
    "POSITION_UPLOAD_INTERVAL",
    "SOS_ALARM",
    "UNKNOWN_B3",
)

### Deframer ###

MAXBUFFER: int = 4096


class StreamError(Exception):
    pass


class GPS303Conn:
    def __init__(self) -> None:
        self.buffer = b""

    @staticmethod
    def enframe(buffer: bytes) -> bytes:
        return b"xx" + buffer + b"\r\n"

    def recv(self, segment: bytes) -> List[bytes]:
        when = time()
        self.buffer += segment
        if len(self.buffer) > MAXBUFFER:
            # We are receiving junk. Let's drop it or we run out of memory.
            self.buffer = b""
            raise StreamError(
                f"More than {MAXBUFFER} unparseable data, dropping"
            )
        msgs = []
        while True:
            framestart = self.buffer.find(b"xx")
            if framestart == -1:  # No frames, return whatever we have
                break
            if framestart > 0:  # Should not happen, report
                self.buffer = self.buffer[framestart:]
                raise StreamError(
                    f'Undecodable data ({framestart}) "{self.buffer[:framestart][:64].hex()}"'
                )
            # At this point, buffer starts with a packet
            if len(self.buffer) < 6:  # no len and proto - cannot proceed
                break
            exp_end = self.buffer[2] + 3  # Expect '\r\n' here
            frameend = 0
            # Length field can legitimeely be much less than the
            # length of the packet (e.g. WiFi positioning), but
            # it _should not_ be greater. Still sometimes it is.
            # Luckily, not by too much: by maybe two or three bytes?
            # Do this embarrassing hack to avoid accidental match
            # of some binary data in the packet against '\r\n'.
            while True:
                frameend = self.buffer.find(b"\r\n", frameend + 1)
                if frameend == -1 or frameend >= (
                    exp_end - 3
                ):  # Found realistic match or none
                    break
            if frameend == -1:  # Incomplete frame, return what we have
                break
            packet = self.buffer[2:frameend]
            self.buffer = self.buffer[frameend + 2 :]
            if len(packet) < 2:  # frameend comes too early
                raise StreamError(f"Packet too short: {packet.hex()}")
            msgs.append(packet)
        return msgs

    def close(self) -> bytes:
        ret = self.buffer
        self.buffer = b""
        return ret


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


def hhmm(x: str) -> str:
    """Check for the string that represents hours and minutes"""
    if not isinstance(x, str) or len(x) != 4:
        raise ValueError(str(x) + " is not a four-character string")
    hh = int(x[:2])
    mm = int(x[2:])
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        raise ValueError(str(x) + " does not contain valid hours and minutes")
    return x


def hhmmhhmm(x: str) -> str:
    """Check for the string that represents hours and minutes twice"""
    if not isinstance(x, str) or len(x) != 8:
        raise ValueError(str(x) + " is not an eight-character string")
    return hhmm(x[:4]) + hhmm(x[4:])


def l3str(x: Union[str, List[str]]) -> List[str]:
    if isinstance(x, str):
        lx = x.split(",")
    else:
        lx = x
    if len(lx) != 3 or not all(isinstance(el, str) for el in x):
        raise ValueError(str(lx) + " is not a list of three strings")
    return lx


def l3alarms(x: Union[str, List[Tuple[int, str]]]) -> List[Tuple[int, str]]:
    def alrmspec(sub: str) -> Tuple[int, str]:
        if len(sub) != 7:
            raise ValueError(sub + " does not represent day and time")
        return (
            {
                "MON": 1,
                "TUE": 2,
                "WED": 3,
                "THU": 4,
                "FRI": 5,
                "SAT": 6,
                "SUN": 7,
            }[sub[:3].upper()],
            sub[3:],
        )

    if isinstance(x, str):
        lx = [alrmspec(sub) for sub in x.split(",")]
    else:
        lx = x
    lx.extend([(0, "0000") for _ in range(3 - len(lx))])
    if len(lx) != 3 or any(d < 0 or d > 7 for d, tm in lx):
        raise ValueError(str(lx) + " is a wrong alarms specification")
    return [(d, hhmm(tm)) for d, tm in lx]


def l3int(x: Union[str, List[int]]) -> List[int]:
    if isinstance(x, str):
        lx = [int(el) for el in x.split(",")]
    else:
        lx = x
    if len(lx) != 3 or not all(isinstance(el, int) for el in lx):
        raise ValueError(str(lx) + " is not a list of three integers")
    return lx


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


class GPS303Pkt(metaclass=MetaPkt):
    RESPOND = Respond.NON  # Do not send anything back by default
    PROTO: int
    IN_KWARGS: Tuple[Tuple[str, Callable[[Any], Any], Any], ...] = ()
    OUT_KWARGS: Tuple[Tuple[str, Callable[[Any], Any], Any], ...] = ()
    KWARGS: Tuple[Tuple[str, Callable[[Any], Any], Any], ...] = ()
    In: Type["GPS303Pkt"]
    Out: Type["GPS303Pkt"]

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
        assert not args or (len(args) == 2 and not kwargs)
        if args:  # guaranteed to be two arguments at this point
            self.length, self.payload = args
            try:
                self.decode(self.length, self.payload)
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

    decode: Callable[["GPS303Pkt", int, bytes], None]

    def in_decode(self, length: int, packet: bytes) -> None:
        # Overridden in subclasses, otherwise do not decode payload
        return

    def out_decode(self, length: int, packet: bytes) -> None:
        # Overridden in subclasses, otherwise do not decode payload
        return

    encode: Callable[["GPS303Pkt"], bytes]

    def in_encode(self) -> bytes:
        # Necessary to emulate terminal, which is not implemented
        raise NotImplementedError(
            self.__class__.__name__ + ".encode() not implemented"
        )

    def out_encode(self) -> bytes:
        # Overridden in subclasses, otherwise make empty payload
        return b""

    @property
    def packed(self) -> bytes:
        payload = self.encode()
        length = getattr(self, "length", len(payload) + 1)
        return pack("BB", length, self.PROTO) + payload


class UNKNOWN(GPS303Pkt):
    PROTO = 256  # > 255 is impossible in real packets


class LOGIN(GPS303Pkt):
    PROTO = 0x01
    RESPOND = Respond.INL
    # Default response for ACK, can also respond with STOP_UPLOAD
    IN_KWARGS = (("imei", str, "0000000000000000"), ("ver", int, 0))

    def in_decode(self, length: int, payload: bytes) -> None:
        self.imei = payload[:8].ljust(8, b"\0").hex()
        self.ver = payload[8]

    def in_encode(self) -> bytes:
        return bytes.fromhex(self.imei).ljust(8, b"\0")[:8] + pack(
            "B", self.ver
        )


class SUPERVISION(GPS303Pkt):
    PROTO = 0x05
    OUT_KWARGS = (("status", int, 1),)

    def out_encode(self) -> bytes:
        # 1: The device automatically answers Pickup effect
        # 2: Automatically Answering Two-way Calls
        # 3: Ring manually answer the two-way call
        return pack("B", self.status)


class HEARTBEAT(GPS303Pkt):
    PROTO = 0x08
    RESPOND = Respond.INL


class _GPS_POSITIONING(GPS303Pkt):
    RESPOND = Respond.INL

    def in_decode(self, length: int, payload: bytes) -> None:
        self.dtime = payload[:6]
        if self.dtime == b"\0\0\0\0\0\0":
            self.devtime = None
        else:
            yr, mo, da, hr, mi, se = unpack("BBBBBB", self.dtime)
            self.devtime = datetime(
                2000 + yr, mo, da, hr, mi, se, tzinfo=timezone.utc
            )
        self.gps_data_length = payload[6] >> 4
        self.gps_nb_sat = payload[6] & 0x0F
        lat, lon, speed, flags = unpack("!IIBH", payload[7:18])
        self.gps_is_valid = bool(flags & 0b0001000000000000)  # bit 3
        flip_lon = bool(flags & 0b0000100000000000)  # bit 4
        flip_lat = not bool(flags & 0b0000010000000000)  # bit 5
        self.heading = flags & 0b0000001111111111  # bits 6 - last
        self.latitude = lat / (30000 * 60) * (-1 if flip_lat else 1)
        self.longitude = lon / (30000 * 60) * (-1 if flip_lon else 1)
        self.speed = speed
        self.flags = flags

    def out_encode(self) -> bytes:
        tup = datetime.utcnow().timetuple()
        ttup = (tup[0] % 100,) + tup[1:6]
        return pack("BBBBBB", *ttup)


class GPS_POSITIONING(_GPS_POSITIONING):
    PROTO = 0x10


class GPS_OFFLINE_POSITIONING(_GPS_POSITIONING):
    PROTO = 0x11


class STATUS(GPS303Pkt):
    PROTO = 0x13
    RESPOND = Respond.EXT
    IN_KWARGS = (
        ("batt", int, 100),
        ("ver", int, 0),
        ("timezone", int, 0),
        ("intvl", int, 0),
        ("signal", maybe(int), None),
    )
    OUT_KWARGS = (("upload_interval", int, 25),)

    def in_decode(self, length: int, payload: bytes) -> None:
        self.batt, self.ver, self.timezone, self.intvl = unpack(
            "BBBB", payload[:4]
        )
        if len(payload) > 4:
            self.signal: Optional[int] = payload[4]
        else:
            self.signal = None

    def in_encode(self) -> bytes:
        return pack("BBBB", self.batt, self.ver, self.timezone, self.intvl) + (
            b"" if self.signal is None else pack("B", self.signal)
        )

    def out_encode(self) -> bytes:  # Set interval in minutes
        return pack("B", self.upload_interval)


class HIBERNATION(GPS303Pkt):  # Server can send to send devicee to sleep
    PROTO = 0x14

    def in_encode(self) -> bytes:
        return b""


class RESET(GPS303Pkt):
    # Device sends when it got reset SMS
    # Server can send to initiate factory reset
    PROTO = 0x15


class WHITELIST_TOTAL(GPS303Pkt):  # Server sends to initiage sync (0x58)
    PROTO = 0x16
    OUT_KWARGS = (("number", int, 3),)

    def out_encode(self) -> bytes:  # Number of whitelist entries
        return pack("B", self.number)


class _WIFI_POSITIONING(GPS303Pkt):
    IN_KWARGS: Tuple[Tuple[str, Callable[[Any], Any], Any], ...] = (
        # IN_KWARGS = (
        ("dtime", bytes, b"\0\0\0\0\0\0"),
        ("wifi_aps", list, []),
        ("mcc", int, 0),
        ("mnc", int, 0),
        ("gsm_cells", list, []),
    )

    def in_decode(self, length: int, payload: bytes) -> None:
        self.dtime = payload[:6]
        if self.dtime == b"\0\0\0\0\0\0":
            self.devtime = None
        else:
            self.devtime = datetime.strptime(
                self.dtime.hex(), "%y%m%d%H%M%S"
            ).astimezone(tz=timezone.utc)
        self.wifi_aps = []
        for i in range(self.length):  # length has special meaning here
            slice = payload[6 + i * 7 : 13 + i * 7]
            self.wifi_aps.append(
                (":".join([format(b, "02X") for b in slice[:6]]), -slice[6])
            )
        gsm_slice = payload[6 + self.length * 7 :]
        ncells, self.mcc, self.mnc = unpack("!BHB", gsm_slice[:4])
        self.gsm_cells = []
        for i in range(ncells):
            slice = gsm_slice[4 + i * 5 : 9 + i * 5]
            locac, cellid, sigstr = unpack(
                "!HHB", gsm_slice[4 + i * 5 : 9 + i * 5]
            )
            self.gsm_cells.append((locac, cellid, -sigstr))

    def in_encode(self) -> bytes:
        self.length = len(self.wifi_aps)
        return b"".join(
            [
                self.dtime,
                b"".join(
                    [
                        bytes.fromhex(mac.replace(":", "")).ljust(6, b"\0")[:6]
                        + pack("B", -sigstr)
                        for mac, sigstr in self.wifi_aps
                    ]
                ),
                pack("!BHB", len(self.gsm_cells), self.mcc, self.mnc),
                b"".join(
                    [
                        pack("!HHB", locac, cellid, -sigstr)
                        for locac, cellid, sigstr in self.gsm_cells
                    ]
                ),
            ]
        )


class WIFI_OFFLINE_POSITIONING(_WIFI_POSITIONING):
    PROTO = 0x17
    RESPOND = Respond.INL

    def out_encode(self) -> bytes:
        return bytes.fromhex(datetime.utcnow().strftime("%y%m%d%H%M%S"))


class TIME(GPS303Pkt):
    PROTO = 0x30
    RESPOND = Respond.INL

    def out_encode(self) -> bytes:
        return pack("!HBBBBB", *datetime.utcnow().timetuple()[:6])


class PROHIBIT_LBS(GPS303Pkt):
    PROTO = 0x33
    OUT_KWARGS = (("status", int, 1),)

    def out_encode(self) -> bytes:  # Server sent, 0-off, 1-on
        return pack("B", self.status)


class GPS_LBS_SWITCH_TIMES(GPS303Pkt):
    PROTO = 0x34

    OUT_KWARGS = (
        ("gps_off", boolx, False),  # Clarify the meaning of 0/1
        ("gps_interval_set", boolx, False),
        ("gps_interval", hhmmhhmm, "00000000"),
        ("lbs_off", boolx, False),  # Clarify the meaning of 0/1
        ("boot_time_set", boolx, False),
        ("boot_time", hhmm, "0000"),
        ("shut_time_set", boolx, False),
        ("shut_time", hhmm, "0000"),
    )

    def out_encode(self) -> bytes:
        return (
            pack("B", self.gps_off)
            + pack("B", self.gps_interval_set)
            + bytes.fromhex(self.gps_interval)
            + pack("B", self.lbs_off)
            + pack("B", self.boot_time_set)
            + bytes.fromhex(self.boot_time)
            + pack("B", self.shut_time_set)
            + bytes.fromhex(self.shut_time)
        )


class _SET_PHONE(GPS303Pkt):
    OUT_KWARGS = (("phone", str, ""),)

    def out_encode(self) -> bytes:
        self.phone: str
        return self.phone.encode("")


class REMOTE_MONITOR_PHONE(_SET_PHONE):
    PROTO = 0x40


class SOS_PHONE(_SET_PHONE):
    PROTO = 0x41


class DAD_PHONE(_SET_PHONE):
    PROTO = 0x42


class MOM_PHONE(_SET_PHONE):
    PROTO = 0x43


class STOP_UPLOAD(GPS303Pkt):  # Server response to LOGIN to thwart the device
    PROTO = 0x44


class GPS_OFF_PERIOD(GPS303Pkt):
    PROTO = 0x46
    OUT_KWARGS = (
        ("onoff", int, 0),
        ("fm", hhmm, "0000"),
        ("to", hhmm, "2359"),
    )

    def out_encode(self) -> bytes:
        return (
            pack("B", self.onoff)
            + bytes.fromhex(self.fm)
            + bytes.fromhex(self.to)
        )


class DND_PERIOD(GPS303Pkt):
    PROTO = 0x47
    OUT_KWARGS = (
        ("onoff", int, 0),
        ("week", int, 3),
        ("fm1", hhmm, "0000"),
        ("to1", hhmm, "2359"),
        ("fm2", hhmm, "0000"),
        ("to2", hhmm, "2359"),
    )

    def out_encode(self) -> bytes:
        return (
            pack("B", self.onoff)
            + pack("B", self.week)
            + bytes.fromhex(self.fm1)
            + bytes.fromhex(self.to1)
            + bytes.fromhex(self.fm2)
            + bytes.fromhex(self.to2)
        )


class RESTART_SHUTDOWN(GPS303Pkt):
    PROTO = 0x48
    OUT_KWARGS = (("flag", int, 0),)

    def out_encode(self) -> bytes:
        # 1 - restart
        # 2 - shutdown
        return pack("B", self.flag)


class DEVICE(GPS303Pkt):
    PROTO = 0x49
    OUT_KWARGS = (("flag", int, 0),)

    # 0 - Stop looking for equipment
    # 1 - Start looking for equipment
    def out_encode(self) -> bytes:
        return pack("B", self.flag)


class ALARM_CLOCK(GPS303Pkt):
    PROTO = 0x50
    OUT_KWARGS: Tuple[
        Tuple[str, Callable[[Any], Any], List[Tuple[int, str]]], ...
    ] = (
        ("alarms", l3alarms, []),
    )

    def out_encode(self) -> bytes:
        return b"".join(
            pack("B", day) + bytes.fromhex(tm) for day, tm in self.alarms
        )


class STOP_ALARM(GPS303Pkt):
    PROTO = 0x56

    def in_decode(self, length: int, payload: bytes) -> None:
        self.flag = payload[0]


class SETUP(GPS303Pkt):
    PROTO = 0x57
    RESPOND = Respond.EXT
    OUT_KWARGS = (
        ("uploadintervalseconds", intx, 0x0300),
        ("binaryswitch", intx, 0b00110001),
        ("alarms", l3int, [0, 0, 0]),
        ("dndtimeswitch", int, 0),
        ("dndtimes", l3int, [0, 0, 0]),
        ("gpstimeswitch", int, 0),
        ("gpstimestart", int, 0),
        ("gpstimestop", int, 0),
        ("phonenumbers", l3str, ["", "", ""]),
    )

    def out_encode(self) -> bytes:
        def pack3b(x: int) -> bytes:
            return pack("!I", x)[1:]

        return b"".join(
            [
                pack("!H", self.uploadintervalseconds),
                pack("B", self.binaryswitch),
            ]
            + [pack3b(el) for el in self.alarms]
            + [
                pack("B", self.dndtimeswitch),
            ]
            + [pack3b(el) for el in self.dndtimes]
            + [
                pack("B", self.gpstimeswitch),
                pack("!H", self.gpstimestart),
                pack("!H", self.gpstimestop),
            ]
            + [b";".join([el.encode() for el in self.phonenumbers])]
        )

    def in_encode(self) -> bytes:
        return b""


class SYNCHRONOUS_WHITELIST(GPS303Pkt):
    PROTO = 0x58


class RESTORE_PASSWORD(GPS303Pkt):
    PROTO = 0x67


class WIFI_POSITIONING(_WIFI_POSITIONING):
    PROTO = 0x69
    RESPOND = Respond.EXT
    OUT_KWARGS = (("latitude", float, None), ("longitude", float, None))

    def out_encode(self) -> bytes:
        if self.latitude is None or self.longitude is None:
            return b""
        return "{:+#010.8g},{:+#010.8g}".format(
            self.latitude, self.longitude
        ).encode()

    def out_decode(self, length: int, payload: bytes) -> None:
        lat, lon = payload.decode().split(",")
        self.latitude = float(lat)
        self.longitude = float(lon)


class MANUAL_POSITIONING(GPS303Pkt):
    PROTO = 0x80

    def in_decode(self, length: int, payload: bytes) -> None:
        self.flag = payload[0] if len(payload) > 0 else -1
        self.reason = {
            1: "Incorrect time",
            2: "LBS less",
            3: "WiFi less",
            4: "LBS search > 3 times",
            5: "Same LBS and WiFi data",
            6: "LBS prohibited, WiFi absent",
            7: "GPS spacing < 50 m",
        }.get(self.flag, "Unknown")


class BATTERY_CHARGE(GPS303Pkt):
    PROTO = 0x81


class CHARGER_CONNECTED(GPS303Pkt):
    PROTO = 0x82


class CHARGER_DISCONNECTED(GPS303Pkt):
    PROTO = 0x83


class VIBRATION_RECEIVED(GPS303Pkt):
    PROTO = 0x94


class POSITION_UPLOAD_INTERVAL(GPS303Pkt):
    PROTO = 0x98
    RESPOND = Respond.EXT
    OUT_KWARGS = (("interval", int, 10),)

    def in_decode(self, length: int, payload: bytes) -> None:
        self.interval = unpack("!H", payload[:2])

    def out_encode(self) -> bytes:
        return pack("!H", self.interval)


class SOS_ALARM(GPS303Pkt):
    PROTO = 0x99


class UNKNOWN_B3(GPS303Pkt):
    PROTO = 0xB3
    IN_KWARGS = (("asciidata", str, ""),)

    def in_decode(self, length: int, payload: bytes) -> None:
        self.asciidata = payload.decode()


# Build dicts protocol number -> class and class name -> protocol number
CLASSES = {}
PROTOS = {}
if True:  # just to indent the code, sorry!
    for cls in [
        cls
        for name, cls in globals().items()
        if isclass(cls)
        and issubclass(cls, GPS303Pkt)
        and not name.startswith("_")
    ]:
        if hasattr(cls, "PROTO"):
            CLASSES[cls.PROTO] = cls
            PROTOS[cls.__name__] = cls.PROTO


def class_by_prefix(
    prefix: str,
) -> Union[Type[GPS303Pkt], List[Tuple[str, int]]]:
    lst = [
        (name, proto)
        for name, proto in PROTOS.items()
        if name.upper().startswith(prefix.upper())
    ]
    if len(lst) != 1:
        return lst
    _, proto = lst[0]
    return CLASSES[proto]


def proto_by_name(name: str) -> int:
    return PROTOS.get(name, -1)


def proto_of_message(packet: bytes) -> int:
    return packet[1]


def inline_response(packet: bytes) -> Optional[bytes]:
    proto = proto_of_message(packet)
    if proto in CLASSES:
        cls = CLASSES[proto]
        if cls.RESPOND is Respond.INL:
            return cls.Out().packed
    return None


def parse_message(packet: bytes, is_incoming: bool = True) -> GPS303Pkt:
    """From a packet (without framing bytes) derive the XXX.In object"""
    length, proto = unpack("BB", packet[:2])
    payload = packet[2:]
    if proto not in CLASSES:
        cause: Union[DecodeError, ValueError, IndexError] = ValueError(
            f"Proto {proto} is unknown"
        )
    else:
        try:
            if is_incoming:
                return CLASSES[proto].In(length, payload)
            else:
                return CLASSES[proto].Out(length, payload)
        except (DecodeError, ValueError, IndexError) as e:
            cause = e
    if is_incoming:
        retobj = UNKNOWN.In(length, payload)
    else:
        retobj = UNKNOWN.Out(length, payload)
    retobj.PROTO = proto  # Override class attr with object attr
    retobj.cause = cause
    return retobj
