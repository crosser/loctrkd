""" Zeromq messages """

from datetime import datetime, timezone
import ipaddress as ip
from struct import pack, unpack

__all__ = "Bcast", "LocEvt", "Resp"


def pack_peer(peeraddr):
    try:
        saddr, port, _x, _y = peeraddr
        addr = ip.ip_address(saddr)
    except ValueError:
        saddr, port = peeraddr
        a4 = ip.ip_address(saddr)
        addr = ip.IPv6Address(b"\0\0\0\0\0\0\0\0\0\0\xff\xff" + a4.packed)
    return addr.packed + pack("!H", port)


def unpack_peer(buffer):
    a6 = ip.IPv6Address(buffer[:16])
    port = unpack("!H", buffer[16:])[0]
    addr = a6.ipv4_mapped
    if addr is None:
        addr = a6
    return (addr, port)


class _Zmsg:
    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            self.decode(args[0])
        elif bool(kwargs):
            for k, v in self.KWARGS:
                setattr(self, k, kwargs.get(k, v))
        else:
            raise RuntimeError(
                self.__class__.__name__
                + ": both args "
                + str(args)
                + " and kwargs "
                + str(kwargs)
            )

    def __repr__(self):
        return "{}({})".format(
            self.__class__.__name__,
            ", ".join(
                [
                    "{}={}".format(
                        k,
                        'bytes.fromhex("{}")'.format(getattr(self, k).hex())
                        if isinstance(getattr(self, k), bytes)
                        else getattr(self, k),
                    )
                    for k, _ in self.KWARGS
                ]
            ),
        )

    def decode(self, buffer):
        raise RuntimeError(
            self.__class__.__name__ + "must implement `encode()` method"
        )

    @property
    def packed(self):
        raise RuntimeError(
            self.__class__.__name__ + "must implement `encode()` method"
        )


class Bcast(_Zmsg):
    """Zmq message to broadcast what was received from the terminal"""

    KWARGS = (
        ("proto", 256),
        ("imei", None),
        ("when", None),
        ("peeraddr", None),
        ("packet", b""),
    )

    @property
    def packed(self):
        return (
            pack("B", self.proto)
            + ("0000000000000000" if self.imei is None else self.imei).encode()
            + (
                b"\0\0\0\0\0\0\0\0"
                if self.when is None
                else pack("!d", self.when)
            )
            + pack_peer(self.peeraddr)
            + self.packet
        )

    def decode(self, buffer):
        self.proto = buffer[0]
        self.imei = buffer[1:17].decode()
        if self.imei == "0000000000000000":
            self.imei = None
        self.when = unpack("!d", buffer[17:25])[0]
        self.peeraddr = unpack_peer(buffer[25:43])
        self.packet = buffer[43:]


class Resp(_Zmsg):
    """Zmq message received from a third party to send to the terminal"""

    KWARGS = (("imei", None), ("packet", b""))

    @property
    def packed(self):
        return (
            "0000000000000000" if self.imei is None else self.imei.encode()
        ) + self.packet

    def decode(self, buffer):
        self.imei = buffer[:16].decode()
        self.packet = buffer[16:]


class LocEvt(_Zmsg):
    """Zmq message with original or approximated location from lookaside"""

    KWARGS = (
        ("imei", "0000000000000000"),
        ("devtime", datetime(1970, 1, 1, tzinfo=timezone.utc)),
        ("lat", 0.0),
        ("lon", 0.0),
        ("is_gps", True),
    )

    @property
    def packed(self):
        return self.imei.encode() + pack(
            "!dddB",
            self.devtime.replace(tzinfo=timezone.utc).timestamp(),
            self.lat,
            self.lon,
            int(self.is_gps),
        )

    def decode(self, buffer):
        self.imei = buffer[:16].decode()
        when, self.lat, self.lon, is_gps = unpack("!dddB", buffer[16:])
        self.devtime = datetime.fromtimestamp(when).astimezone(tz=timezone.utc)
        self.is_gps = bool(is_gps)
