""" Zeromq messages """

import ipaddress as ip
from struct import pack, unpack

__all__ = "Bcast", "Resp"

def pack_peer(peeraddr):
    saddr, port, _x, _y = peeraddr
    addr6 = ip.ip_address(saddr)
    addr = addr6.ipv4_mapped
    if addr is None:
        addr = addr6
    return pack("B", addr.version) + (addr.packed + b"\0\0\0\0\0\0\0\0\0\0\0\0")[:16] + pack("!H", port)

def unpack_peer(buffer):
    version = buffer[0]
    if version not in (4, 6):
        return None
    if version == 4:
        addr = ip.IPv4Address(buffer[1:5])
    else:
        addr = ip.IPv6Address(buffer[1:17])
    port = unpack("!H", buffer[17:19])[0]
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
            + (b"\0\0\0\0\0\0\0\0" if self.when is None else pack("!d", self.when))
            + pack_peer(self.peeraddr)
            + self.packet
        )

    def decode(self, buffer):
        self.proto = buffer[0]
        self.imei = buffer[1:17].decode()
        if self.imei == "0000000000000000":
            self.imei = None
        self.when = unpack("!d", buffer[17:25])[0]
        self.peeraddr = unpack_peer(buffer[25:44])
        self.packet = buffer[44:]


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
