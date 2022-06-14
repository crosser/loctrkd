""" Zeromq messages """

import ipaddress as ip
from struct import pack, unpack
from typing import Any, cast, Optional, Tuple, Type, Union

__all__ = "Bcast", "Resp", "topic"


def pack_peer(
    peeraddr: Union[None, Tuple[str, int], Tuple[str, int, Any, Any]]
) -> bytes:
    if peeraddr is None:
        addr: Union[ip.IPv4Address, ip.IPv6Address] = ip.IPv6Address(0)
        port = 0
    elif len(peeraddr) == 2:
        peeraddr = cast(Tuple[str, int], peeraddr)
        saddr, port = peeraddr
        addr = ip.ip_address(saddr)
    elif len(peeraddr) == 4:
        peeraddr = cast(Tuple[str, int, Any, Any], peeraddr)
        saddr, port, _x, _y = peeraddr
        addr = ip.ip_address(saddr)
    if isinstance(addr, ip.IPv4Address):
        addr = ip.IPv6Address(b"\0\0\0\0\0\0\0\0\0\0\xff\xff" + addr.packed)
    return addr.packed + pack("!H", port)


def unpack_peer(
    buffer: bytes,
) -> Tuple[str, int]:
    a6 = ip.IPv6Address(buffer[:16])
    port = unpack("!H", buffer[16:])[0]
    a4 = a6.ipv4_mapped
    if a4 is not None:
        return (str(a4), port)
    elif a6 == ip.IPv6Address("::"):
        return ("", 0)
    return (str(a6), port)


class _Zmsg:
    KWARGS: Tuple[Tuple[str, Any], ...]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
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

    def __repr__(self) -> str:
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

    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return all(
                [getattr(self, k) == getattr(other, k) for k, _ in self.KWARGS]
            )
        return NotImplemented

    def decode(self, buffer: bytes) -> None:
        raise NotImplementedError(
            self.__class__.__name__ + "must implement `decode()` method"
        )

    @property
    def packed(self) -> bytes:
        raise NotImplementedError(
            self.__class__.__name__ + "must implement `packed()` property"
        )


def topic(
    proto: int, is_incoming: bool = True, imei: Optional[str] = None
) -> bytes:
    return pack("BB", is_incoming, proto) + (
        b"" if imei is None else pack("16s", imei.encode())
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
    def packed(self) -> bytes:
        return (
            pack(
                "BB16s",
                int(self.is_incoming),
                self.proto,
                b"0000000000000000"
                if self.imei is None
                else self.imei.encode(),
            )
            + (
                b"\0\0\0\0\0\0\0\0"
                if self.when is None
                else pack("!d", self.when)
            )
            + pack_peer(self.peeraddr)
            + self.packet
        )

    def decode(self, buffer: bytes) -> None:
        self.is_incoming = bool(buffer[0])
        self.proto = buffer[1]
        self.imei: Optional[str] = buffer[2:18].decode()
        if self.imei == "0000000000000000":
            self.imei = None
        self.when = unpack("!d", buffer[18:26])[0]
        self.peeraddr = unpack_peer(buffer[26:44])
        self.packet = buffer[44:]


class Resp(_Zmsg):
    """Zmq message received from a third party to send to the terminal"""

    KWARGS = (("imei", None), ("when", None), ("packet", b""))

    @property
    def packed(self) -> bytes:
        return (
            pack(
                "16s",
                "0000000000000000"
                if self.imei is None
                else self.imei.encode(),
            )
            + (
                b"\0\0\0\0\0\0\0\0"
                if self.when is None
                else pack("!d", self.when)
            )
            + self.packet
        )

    def decode(self, buffer: bytes) -> None:
        self.imei = buffer[:16].decode()
        self.when = unpack("!d", buffer[16:24])[0]
        self.packet = buffer[24:]
