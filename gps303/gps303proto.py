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
from logging import getLogger
from struct import pack, unpack

__all__ = (
    "class_by_prefix",
    "inline_response",
    "make_object",
    "parse_message",
    "proto_by_name",
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
    "MOM_PHONE",
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
)

log = getLogger("gps303")


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

    def __new__(cls, name, bases, attrs):
        newcls = super().__new__(cls, name, bases, attrs)
        newcls.In = super().__new__(
            cls,
            name + ".In",
            (newcls,) + bases,
            {"KWARGS": newcls.IN_KWARGS, "encode": newcls.in_encode},
        )
        newcls.Out = super().__new__(
            cls,
            name + ".Out",
            (newcls,) + bases,
            {"KWARGS": newcls.OUT_KWARGS, "encode": newcls.out_encode},
        )
        return newcls


class Respond(Enum):
    NON = 0  # Incoming, no response needed
    INL = 1  # Birirectional, use `inline_response()`
    EXT = 2  # Birirectional, use external responder


class GPS303Pkt(metaclass=MetaPkt):
    RESPOND = Respond.NON  # Do not send anything back by default
    PROTO: int
    # Have these kwargs for now, TODO redo
    IN_KWARGS = (("length", int, 0), ("payload", bytes, b""))
    OUT_KWARGS = ()

    def __init__(self, *args, **kwargs):
        assert len(args) == 0
        for kw, typ, dfl in self.KWARGS:
            setattr(self, kw, typ(kwargs.pop(kw, dfl)))
        if kwargs:
            print("KWARGS", self.KWARGS)
            print("kwargs", kwargs)
            raise TypeError(
                self.__class__.__name__ + " stray kwargs " + str(kwargs)
            )

    def __repr__(self):
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

    def in_encode(self):
        raise NotImplementedError(
            self.__class__.__name__ + ".encode() not implemented"
        )

    def out_encode(self):
        return b""

    @property
    def packed(self):
        payload = self.encode()
        length = len(payload) + 1
        return pack("BB", length, self.PROTO) + payload

    @classmethod
    def from_packet(cls, length, payload):
        return cls.In(payload=payload, length=length)


class UNKNOWN(GPS303Pkt):
    PROTO = 256  # > 255 is impossible in real packets


class LOGIN(GPS303Pkt):
    PROTO = 0x01
    RESPOND = Respond.INL
    # Default response for ACK, can also respond with STOP_UPLOAD

    @classmethod
    def from_packet(cls, length, payload):
        self = super().from_packet(length, payload)
        self.imei = payload[:-1].hex()
        self.ver = unpack("B", payload[-1:])[0]
        return self


class SUPERVISION(GPS303Pkt):
    PROTO = 0x05
    OUT_KWARGS = (("status", int, 1),)

    def out_encode(self):
        # 1: The device automatically answers Pickup effect
        # 2: Automatically Answering Two-way Calls
        # 3: Ring manually answer the two-way call
        return pack("B", self.status)


class HEARTBEAT(GPS303Pkt):
    PROTO = 0x08
    RESPOND = Respond.INL


class _GPS_POSITIONING(GPS303Pkt):
    RESPOND = Respond.INL

    @classmethod
    def from_packet(cls, length, payload):
        self = super().from_packet(length, payload)
        self.dtime = payload[:6]
        if self.dtime == b"\0\0\0\0\0\0":
            self.devtime = None
        else:
            self.devtime = datetime(
                *unpack("BBBBBB", self.dtime), tzinfo=timezone.utc
            )
        self.gps_data_length = payload[6] >> 4
        self.gps_nb_sat = payload[6] & 0x0F
        lat, lon, speed, flags = unpack("!IIBH", payload[7:18])
        self.gps_is_valid = bool(flags & 0b0001000000000000)  # bit 3
        flip_lon = bool(flags & 0b0000100000000000)  # bit 4
        flip_lat = not bool(flags & 0b0000010000000000)  # bit 5
        self.heading = flags & 0b0000001111111111  # bits 6 - last
        self.latitude = lat / (30000 * 60) * (-1 if flip_lat else 1)
        self.longitude = lon / (30000 * 60) * (-2 if flip_lon else 1)
        self.speed = speed
        self.flags = flags
        return self

    def out_encode(self):
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
    OUT_KWARGS = (("upload_interval", int, 25),)

    @classmethod
    def from_packet(cls, length, payload):
        self = super().from_packet(length, payload)
        if len(payload) == 5:
            (
                self.batt,
                self.ver,
                self.timezone,
                self.intvl,
                self.signal,
            ) = unpack("BBBBB", payload)
        elif len(payload) == 4:
            self.batt, self.ver, self.timezone, self.intvl = unpack(
                "BBBB", payload
            )
            self.signal = None
        return self

    def out_encode(self):  # Set interval in minutes
        return cls.make_packet(pack("B", self.upload_interval))


class HIBERNATION(GPS303Pkt):  # Server can send to send devicee to sleep
    PROTO = 0x14
    RESPOND = Respond.INL


class RESET(GPS303Pkt):
    # Device sends when it got reset SMS
    # Server can send to initiate factory reset
    PROTO = 0x15


class WHITELIST_TOTAL(GPS303Pkt):  # Server sends to initiage sync (0x58)
    PROTO = 0x16
    OUT_KWARGS = (("number", int, 3),)

    def out_encode(self):  # Number of whitelist entries
        return pack("B", number)


class _WIFI_POSITIONING(GPS303Pkt):
    @classmethod
    def from_packet(cls, length, payload):
        self = super().from_packet(length, payload)
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
        return self


class WIFI_OFFLINE_POSITIONING(_WIFI_POSITIONING):
    PROTO = 0x17
    RESPOND = Respond.INL

    def out_encode(self):
        return bytes.fromhex(datetime.utcnow().strftime("%y%m%d%H%M%S"))


class TIME(GPS303Pkt):
    PROTO = 0x30
    RESPOND = Respond.INL

    def out_encode(self):
        return pack("!HBBBBB", *datetime.utcnow().timetuple()[:6])


class PROHIBIT_LBS(GPS303Pkt):
    PROTO = 0x33
    OUT_KWARGS = (("status", int, 1),)

    def out_encode(self):  # Server sent, 0-off, 1-on
        return pack("B", self.status)


class GPS_LBS_SWITCH_TIMES(GPS303Pkt):
    PROTO = 0x34

    # Data is in packed decimal
    # 00/01 - GPS on/off
    # 00/01 - Don't set / Set upload period
    # HHMMHHMM - Upload period
    # 00/01 - LBS on/off
    # 00/01 - Don't set / Set time of boot
    # HHMM  - Time of boot
    # 00/01 - Don't set / Set time of shutdown
    # HHMM  - Time of shutdown
    def out_encode(self):
        return b""  # TODO


class _SET_PHONE(GPS303Pkt):
    OUT_KWARGS = (("phone", str, ""),)

    def out_encode(self):
        return self.phone.encode()


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
    OUT_KWARGS = (("onoff", int, 0), ("fm", str, "0000"), ("to", str, "2359"))

    def out_encode(self):
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
        ("fm1", str, "0000"),
        ("to1", str, "2359"),
        ("fm2", str, "0000"),
        ("to2", str, "2359"),
    )

    def out_endode(self):
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
    OUT_KWARGS = (("flag", int, 2),)

    def out_encode(self):
        # 1 - restart
        # 2 - shutdown
        return pack("B", self.flag)


class DEVICE(GPS303Pkt):
    PROTO = 0x49
    OUT_KWARGS = (("flag", int, 0),)

    # 0 - Stop looking for equipment
    # 1 - Start looking for equipment
    def out_encode(self):
        return pack("B", self.flag)


class ALARM_CLOCK(GPS303Pkt):
    PROTO = 0x50

    def out_encode(self):
        # TODO implement parsing kwargs
        alarms = ((0, "0000"), (0, "0000"), (0, "0000"))
        return b"".join(
            cls("B", day) + bytes.fromhex(tm) for day, tm in alarms
        )


class STOP_ALARM(GPS303Pkt):
    PROTO = 0x56

    @classmethod
    def from_packet(cls, length, payload):
        self = super().from_packet(length, payload)
        self.flag = payload[0]
        return self


class SETUP(GPS303Pkt):
    PROTO = 0x57
    RESPOND = Respond.EXT
    OUT_KWARGS = (  # TODO handle properly
        ("uploadintervalseconds", int, 0x0300),
        ("binaryswitch", int, 0b00110001),
        ("alarms", lambda x: x, [0, 0, 0]),
        ("dndtimeswitch", int, 0),
        ("dndtimes", lambda x: x, [0, 0, 0]),
        ("gpstimeswitch", int, 0),
        ("gpstimestart", int, 0),
        ("gpstimestop", int, 0),
        ("phonenumbers", lambda x: x, ["", "", ""]),
    )

    def out_encode(self):
        def pack3b(x):
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


class SYNCHRONOUS_WHITELIST(GPS303Pkt):
    PROTO = 0x58


class RESTORE_PASSWORD(GPS303Pkt):
    PROTO = 0x67


class WIFI_POSITIONING(_WIFI_POSITIONING):
    PROTO = 0x69
    RESPOND = Respond.EXT
    OUT_KWARGS = (("lat", float, None), ("lon", float, None))

    def out_encode(self):
        if self.lat is None or self.lon is None:
            return b""
        return "{:+#010.8g},{:+#010.8g}".format(self.lat, self.lon).encode()


class MANUAL_POSITIONING(GPS303Pkt):
    PROTO = 0x80

    @classmethod
    def from_packet(cls, length, payload):
        self = super().from_packet(length, payload)
        self.flag = payload[0] if len(payload) > 0 else None
        self.reason = {
            1: "Incorrect time",
            2: "LBS less",
            3: "WiFi less",
            4: "LBS search > 3 times",
            5: "Same LBS and WiFi data",
            6: "LBS prohibited, WiFi absent",
            7: "GPS spacing < 50 m",
        }.get(self.flag, "Unknown")
        return self


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

    @classmethod
    def from_packet(cls, length, payload):
        self = super().from_packet(length, payload)
        self.interval = unpack("!H", payload[:2])
        return self

    def out_encode(self):
        return pack("!H", interval)


class SOS_ALARM(GPS303Pkt):
    PROTO = 0x99


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


def class_by_prefix(prefix):
    lst = [
        (name, proto)
        for name, proto in PROTOS.items()
        if name.upper().startswith(prefix.upper())
    ]
    if len(lst) != 1:
        return lst
    _, proto = lst[0]
    return CLASSES[proto]


def proto_by_name(name):
    return PROTOS.get(name, -1)


def proto_of_message(packet):
    return unpack("B", packet[1:2])[0]


def inline_response(packet):
    proto = proto_of_message(packet)
    if proto in CLASSES:
        cls = CLASSES[proto]
        if cls.RESPOND is Respond.INL:
            return cls.Out().packed
    return None


def make_object(length, proto, payload):
    if proto in CLASSES:
        return CLASSES[proto].from_packet(length, payload)
    else:
        retobj = UNKNOWN.from_packet(length, payload)
        retobj.PROTO = proto  # Override class attr with object attr
        return retobj


def parse_message(packet):
    length, proto = unpack("BB", packet[:2])
    payload = packet[2:]
    adjust = 2 if proto == STATUS.PROTO else 4  # Weird special case
    if (
        proto not in (WIFI_POSITIONING.PROTO, WIFI_OFFLINE_POSITIONING.PROTO)
        and length > 1
        and len(payload) + adjust != length
    ):
        log.warning(
            "With proto %d length is %d but payload length is %d+%d",
            proto,
            length,
            len(payload),
            adjust,
        )
    return make_object(length, proto, payload)
