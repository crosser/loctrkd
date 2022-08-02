""" Zeromq messages """

import ipaddress as ip
from struct import pack, unpack
from typing import Any, cast, Optional, Tuple, Type, Union

__all__ = "Bcast", "Resp", "topic", "rtopic"


def pack_peer(  # 18 bytes
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
    proto: str, is_incoming: bool = True, imei: Optional[str] = None
) -> bytes:
    return pack("B16s", is_incoming, proto.encode()) + (
        b"" if imei is None else pack("16s", imei.encode())
    )


def rtopic(imei: str) -> bytes:
    return pack("16s", imei.encode())


class Bcast(_Zmsg):
    """Zmq message to broadcast what was received from the terminal"""

    KWARGS = (
        ("is_incoming", True),
        ("proto", "UNKNOWN"),
        ("imei", None),
        ("when", None),
        ("peeraddr", None),
        ("packet", b""),
    )

    @property
    def packed(self) -> bytes:
        return (
            pack(
                "!B16s16sd",
                int(self.is_incoming),
                self.proto[:16].ljust(16, "\0").encode(),
                b"0000000000000000"
                if self.imei is None
                else self.imei.encode(),
                0 if self.when is None else self.when,
            )
            + pack_peer(self.peeraddr)
            + self.packet
        )

    def decode(self, buffer: bytes) -> None:
        is_incoming, proto, imei, when = unpack("!B16s16sd", buffer[:41])
        self.is_incoming = bool(is_incoming)
        self.proto = proto.decode().rstrip("\0")
        self.imei = (
            None if imei == b"0000000000000000" else imei.decode().strip("\0")
        )
        self.when = when
        self.peeraddr = unpack_peer(buffer[41:59])
        self.packet = buffer[59:]


class Resp(_Zmsg):
    """Zmq message received from a third party to send to the terminal"""

    KWARGS = (("imei", None), ("when", None), ("packet", b""))

    @property
    def packed(self) -> bytes:
        return (
            pack(
                "!16sd",
                "0000000000000000"
                if self.imei is None
                else self.imei.encode(),
                0 if self.when is None else self.when,
            )
            + self.packet
        )

    def decode(self, buffer: bytes) -> None:
        imei, when = unpack("!16sd", buffer[:24])
        self.imei = (
            None if imei == b"0000000000000000" else imei.decode().strip("\0")
        )

        self.when = when
        self.packet = buffer[24:]


class Rept(_Zmsg):
    """Broadcast Zzmq message with "rectified" proto-agnostic json data"""

    KWARGS = (("imei", None), ("payload", ""))

    @property
    def packed(self) -> bytes:
        return (
            pack(
                "16s",
                "0000000000000000"
                if self.imei is None
                else self.imei.encode(),
            )
            + self.payload.encode()
        )

    def decode(self, buffer: bytes) -> None:
        imei = buffer[:16]
        self.imei = (
            None if imei == b"0000000000000000" else imei.decode().strip("\0")
        )
        self.payload = buffer[16:].decode()
