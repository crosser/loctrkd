"""
Implementation of the protocol used by zx303 GPS+GPRS module
Description from https://github.com/tobadia/petGPS/tree/master/resources
"""

from datetime import datetime, timezone
from inspect import isclass
from logging import getLogger
from struct import pack, unpack

__all__ = (
    "handle_packet",
    "make_object",
    "make_response",
    "set_config",
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


class _GT06pkt:
    PROTO: int
    CONFIG = None

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
    def from_packet(cls, length, proto, payload):
        return cls(proto=proto, payload=payload, length=length)

    def response(self, *args):
        if len(args) == 0:
            return None
        assert len(args) == 1 and isinstance(args[0], bytes)
        payload = args[0]
        length = len(payload) + 1
        if length > 6:
            length -= 6
        return b"xx" + pack("BB", length, self.proto) + payload + b"\r\n"


class UNKNOWN(_GT06pkt):
    pass


class LOGIN(_GT06pkt):
    PROTO = 0x01

    @classmethod
    def from_packet(cls, length, proto, payload):
        self = super().from_packet(length, proto, payload)
        self.imei = payload[:-1].hex()
        self.ver = unpack("B", payload[-1:])[0]
        return self

    def response(self):
        return super().response(b"")


class SUPERVISION(_GT06pkt):
    PROTO = 0x05


class HEARTBEAT(_GT06pkt):
    PROTO = 0x08


class _GPS_POSITIONING(_GT06pkt):
    @classmethod
    def from_packet(cls, length, proto, payload):
        self = super().from_packet(length, proto, payload)
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

    def response(self):
        return super().response(self.dtime)


class GPS_POSITIONING(_GPS_POSITIONING):
    PROTO = 0x10


class GPS_OFFLINE_POSITIONING(_GPS_POSITIONING):
    PROTO = 0x11


class STATUS(_GT06pkt):
    PROTO = 0x13

    @classmethod
    def from_packet(cls, length, proto, payload):
        self = super().from_packet(length, proto, payload)
        if len(payload) == 5:
            self.batt, self.ver, self.intvl, self.signal, _ = unpack(
                "BBBBB", payload
            )
        elif len(payload) == 4:
            self.batt, self.ver, self.intvl, _ = unpack("BBBB", payload)
            self.signal = None
        return self


class HIBERNATION(_GT06pkt):
    PROTO = 0x14


class RESET(_GT06pkt):
    PROTO = 0x15


class WHITELIST_TOTAL(_GT06pkt):
    PROTO = 0x16


class _WIFI_POSITIONING(_GT06pkt):
    @classmethod
    def from_packet(cls, length, proto, payload):
        self = super().from_packet(length, proto, payload)
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

    def response(self):
        return super().response(self.dtime)


class TIME(_GT06pkt):
    PROTO = 0x30

    def response(self):
        payload = pack("!HBBBBB", *datetime.utcnow().timetuple()[:6])
        return super().response(payload)


class MOM_PHONE(_GT06pkt):
    PROTO = 0x43


class STOP_ALARM(_GT06pkt):
    PROTO = 0x56


class SETUP(_GT06pkt):
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


class SYNCHRONOUS_WHITELIST(_GT06pkt):
    PROTO = 0x58


class RESTORE_PASSWORD(_GT06pkt):
    PROTO = 0x67


class WIFI_POSITIONING(_WIFI_POSITIONING):
    PROTO = 0x69

    def response(self):
        payload = b""  # TODO fill payload
        return super().response(payload)


class MANUAL_POSITIONING(_GT06pkt):
    PROTO = 0x80


class BATTERY_CHARGE(_GT06pkt):
    PROTO = 0x81


class CHARGER_CONNECTED(_GT06pkt):
    PROTO = 0x82


class CHARGER_DISCONNECTED(_GT06pkt):
    PROTO = 0x83


class VIBRATION_RECEIVED(_GT06pkt):
    PROTO = 0x94


class POSITION_UPLOAD_INTERVAL(_GT06pkt):
    PROTO = 0x98

    @classmethod
    def from_packet(cls, length, proto, payload):
        self = super().from_packet(length, proto, payload)
        self.interval = unpack("!H", payload[:2])
        return self

    def response(self):
        return super().response(pack("!H", self.interval))


# Build a dict protocol number -> class
CLASSES = {}
if True:  # just to indent the code, sorry!
    for cls in [
        cls
        for name, cls in globals().items()
        if isclass(cls)
        and issubclass(cls, _GT06pkt)
        and not name.startswith("_")
    ]:
        if hasattr(cls, "PROTO"):
            CLASSES[cls.PROTO] = cls


def make_object(length, proto, payload):
    if proto in CLASSES:
        return CLASSES[proto].from_packet(length, proto, payload)
    else:
        return UNKNOWN.from_packet(length, proto, payload)


def handle_packet(packet, addr, when):
    if len(packet) < 6:
        return UNKNOWN.from_packet(0, 0, packet)
    else:
        xx, length, proto = unpack("!2sBB", packet[:4])
        crlf = packet[-2:]
        payload = packet[4:-2]
        adjust = 2 if proto == STATUS.PROTO else 4  # Weird special case
        if (
            proto
            not in (WIFI_POSITIONING.PROTO, WIFI_OFFLINE_POSITIONING.PROTO)
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
        if xx != b"xx" or crlf != b"\r\n":
            return UNKNOWN.from_packet(length, proto, packet)  # full packet
        else:
            return make_object(length, proto, payload)


def make_response(msg):
    return msg.response()


def set_config(config):  # Note that we are setting _class_ attribute
    _GT06pkt.CONFIG = config
