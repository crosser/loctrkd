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
from inspect import isclass
from logging import getLogger
from struct import pack, unpack

__all__ = (
    "handle_packet",
    "inline_response",
    "make_object",
    "make_response",
    "parse_message",
    "proto_by_name",
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


class GPS303Pkt:
    PROTO: int

    def __init__(self, *args, **kwargs):
        assert len(args) == 0
        for k, v in kwargs.items():
            setattr(self, k, v)

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

    @classmethod
    def from_packet(cls, length, payload):
        return cls(payload=payload, length=length)

    def to_packet(self):
        return pack("BB", self.length, self.PROTO) + self.payload

    @classmethod
    def make_packet(cls, payload):
        assert isinstance(payload, bytes)
        length = len(payload) + 1
        if length > 6:
            length -= 6
        return pack("BB", length, cls.PROTO) + payload

    @classmethod
    def inline_response(cls, packet):
        return cls.make_packet(b"")


class UNKNOWN(GPS303Pkt):
    PROTO = 256  # > 255 is impossible in real packets

    @classmethod
    def inline_response(cls, packet):
        return None


class LOGIN(GPS303Pkt):
    PROTO = 0x01

    @classmethod
    def from_packet(cls, length, payload):
        self = super().from_packet(length, payload)
        self.imei = payload[:-1].hex()
        self.ver = unpack("B", payload[-1:])[0]
        return self

    def response(self):
        return self.make_packet(b"")


class SUPERVISION(GPS303Pkt):  # Server sends supervision number status
    PROTO = 0x05

    def response(self, supnum=0):
        # 1: The device automatically answers Pickup effect
        # 2: Automatically Answering Two-way Calls
        # 3: Ring manually answer the two-way call
        return super().response(b"")


class HEARTBEAT(GPS303Pkt):
    PROTO = 0x08


class _GPS_POSITIONING(GPS303Pkt):
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

    @classmethod
    def inline_response(cls, packet):
        return cls.make_packet(packet[2:8])

    def response(self):
        return self.make_packet(self.dtime)


class GPS_POSITIONING(_GPS_POSITIONING):
    PROTO = 0x10


class GPS_OFFLINE_POSITIONING(_GPS_POSITIONING):
    PROTO = 0x11


class STATUS(GPS303Pkt):
    PROTO = 0x13

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

    @classmethod
    def inline_response(cls, packet):
        return None

    def response(self, upload_interval=25):  # Set interval in minutes
        return super().response(pack("B", upload_interval))


class HIBERNATION(GPS303Pkt):
    PROTO = 0x14


class RESET(GPS303Pkt):  # Device sends when it got reset SMS
    PROTO = 0x15

    def response(self):  # Server can send to initiate factory reset
        return self.make_packet(b"")


class WHITELIST_TOTAL(GPS303Pkt):  # Server sends to initiage sync (0x58)
    PROTO = 0x16

    def response(self, number=3):  # Number of whitelist entries
        return super().response(pack("B", number))


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

    @classmethod
    def inline_response(cls, packet):
        return cls.make_packet(packet[2:8])

    def response(self):
        return super().response(self.dtime)


class TIME(GPS303Pkt):
    PROTO = 0x30

    @classmethod
    def inline_response(cls, packet):
        return pack(
            "!BBHBBBBB", 7, cls.PROTO, *datetime.utcnow().timetuple()[:6]
        )

    def response(self):
        payload = pack("!HBBBBB", *datetime.utcnow().timetuple()[:6])
        return super().response(payload)


class PROHIBIT_LBS(GPS303Pkt):
    PROTO = 0x33

    def response(self, status=1):  # Server sent, 0-off, 1-on
        return super().response(pack("B", status))


class MOM_PHONE(GPS303Pkt):
    PROTO = 0x43


class STOP_UPLOAD(GPS303Pkt):  # Server response to LOGIN to thwart the device
    PROTO = 0x44

    def response(self):
        return super().response(b"")


class STOP_ALARM(GPS303Pkt):
    PROTO = 0x56


class SETUP(GPS303Pkt):
    PROTO = 0x57

    def response(
        self,
        uploadIntervalSeconds=0x0300,
        binarySwitch=0b00110001,
        alarms=[0, 0, 0],
        dndTimeSwitch=0,
        dndTimes=[0, 0, 0],
        gpsTimeSwitch=0,
        gpsTimeStart=0,
        gpsTimeStop=0,
        phoneNumbers=["", "", ""],
    ):
        def pack3b(x):
            return pack("!I", x)[1:]

        payload = b"".join(
            [
                pack("!H", uploadIntervalSeconds),
                pack("B", binarySwitch),
            ]
            + [pack3b(el) for el in alarms]
            + [
                pack("B", dndTimeSwitch),
            ]
            + [pack3b(el) for el in dndTimes]
            + [
                pack("B", gpsTimeSwitch),
                pack("!H", gpsTimeStart),
                pack("!H", gpsTimeStop),
            ]
            + [b";".join([el.encode() for el in phoneNumbers])]
        )
        return super().response(payload)


class SYNCHRONOUS_WHITELIST(GPS303Pkt):
    PROTO = 0x58


class RESTORE_PASSWORD(GPS303Pkt):
    PROTO = 0x67


class WIFI_POSITIONING(_WIFI_POSITIONING):
    PROTO = 0x69

    @classmethod
    def inline_response(cls, packet):
        return None

    def response(self, lat=None, lon=None):
        if lat is None or lon is None:
            payload = b""
        else:
            payload = "{:+#010.8g},{:+#010.8g}".format(lat, lon).encode(
                "ascii"
            )
        return self.make_packet(payload)


class MANUAL_POSITIONING(GPS303Pkt):
    PROTO = 0x80


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

    @classmethod
    def from_packet(cls, length, payload):
        self = super().from_packet(length, payload)
        self.interval = unpack("!H", payload[:2])
        return self

    @classmethod
    def inline_response(cls, packet):
        return cls.make_packet(packet[2:4])

    def response(self):
        return self.make_packet(pack("!H", self.interval))


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


def proto_by_name(name):
    return PROTOS.get(name, -1)


def proto_of_message(packet):
    return unpack("B", packet[1:2])[0]


def inline_response(packet):
    proto = proto_of_message(packet)
    if proto in CLASSES:
        return CLASSES[proto].inline_response(packet)
    else:
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


def handle_packet(packet):  # DEPRECATED
    if len(packet) < 6 or packet[:2] != b"xx" or packet[-2:] != b"\r\n":
        return UNKNOWN.from_packet(len(packet), packet)
    return parse_message(packet[2:-2])


def make_response(msg, **kwargs):  # DEPRECATED
    inframe = msg.response(**kwargs)
    return None if inframe is None else b"xx" + inframe + b"\r\n"
