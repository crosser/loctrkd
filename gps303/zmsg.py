""" Zeromq messages """

import ipaddress as ip
from struct import pack, unpack

__all__ = "Bcast", "Resp", "topic"


def pack_peer(peeraddr):
    try:
        if peeraddr is None:
            saddr = "::"
            port = 0
        else:
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

    def __eq__(self, other):
        return all(
            [getattr(self, k) == getattr(other, k) for k, _ in self.KWARGS]
        )

    def decode(self, buffer):
        raise NotImplementedError(
            self.__class__.__name__ + "must implement `decode()` method"
        )

    @property
    def packed(self):
        raise NotImplementedError(
            self.__class__.__name__ + "must implement `packed()` property"
        )


def topic(proto, is_incoming=True, imei=None):
    return (
        pack("BB", is_incoming, proto) + b"" if imei is None else imei.encode()
    )


class Bcast(_Zmsg):
    """Zmq message to broadcast what was received from the terminal"""

    KWARGS = (
        ("is_incoming", True),
        ("proto", 256),
        ("imei", None),
        ("when", None),
        ("peeraddr", None),
        ("packet", b""),
    )

    @property
    def packed(self):
        return (
            pack("BB", int(self.is_incoming), self.proto)
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
        self.is_incoming = bool(buffer[0])
        self.proto = buffer[1]
        self.imei = buffer[2:18].decode()
        if self.imei == "0000000000000000":
            self.imei = None
        self.when = unpack("!d", buffer[18:26])[0]
        self.peeraddr = unpack_peer(buffer[26:44])
        self.packet = buffer[44:]


class Resp(_Zmsg):
    """Zmq message received from a third party to send to the terminal"""

    KWARGS = (("imei", None), ("when", None), ("packet", b""))

    @property
    def packed(self):
        return (
            "0000000000000000" if self.imei is None else self.imei.encode()
        ) + (
                b"\0\0\0\0\0\0\0\0"
                if self.when is None
                else pack("!d", self.when)
            ) + self.packet

    def decode(self, buffer):
        self.imei = buffer[:16].decode()
        self.when = unpack("!d", buffer[16:24])[0]
        self.packet = buffer[24:]
