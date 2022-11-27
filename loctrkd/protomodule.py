""" Things the module implementing a protocol exports """

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    _ProtocolMeta,  # How not to cheat here?!
    Tuple,
    Type,
    TYPE_CHECKING,
    Union,
)


class MetaPkt(type):
    """
    For each class corresponding to a message, automatically create
    two nested classes `In` and `Out` that also inherit from their
    "nest". Class attribute `IN_KWARGS` defined in the "nest" is
    copied to the `In` nested class under the name `KWARGS`, and
    likewise, `OUT_KWARGS` of the nest class is copied as `KWARGS`
    to the nested class `Out`. In addition, methods `encode` and
    `decode` are defined in both classes equal to `in_{en|de}code()`
    and `out_{en|de}code()` respectively.
    """

    if TYPE_CHECKING:

        def __getattr__(self, name: str) -> Any:
            pass

        def __setattr__(self, name: str, value: Any) -> None:
            pass

    def in_decode(self, *args: Any) -> None:
        ...

    def out_decode(self, *args: Any) -> None:
        ...

    def in_encode(self, *args: Any) -> Any:
        ...

    def out_encode(self, *args: Any) -> Any:
        ...

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


# Have to do this to prevent incomprehensible error message:
# TypeError: metaclass conflict: the metaclass of a derived class \
#     must be a (non-strict) subclass of the metaclasses of all its bases
class _MetaProto(_ProtocolMeta, MetaPkt):
    pass


class ProtoClass(Protocol, metaclass=_MetaProto):
    IN_KWARGS: Tuple[Tuple[str, Callable[[Any], Any], Any], ...] = ()
    OUT_KWARGS: Tuple[Tuple[str, Callable[[Any], Any], Any], ...] = ()

    @classmethod
    def proto_name(cls) -> str:
        ...

    class In:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            ...

        def encode(self) -> bytes:
            ...

        def decode(self, *args: Any, **kwargs: Any) -> None:
            ...

        @property
        def packed(self) -> bytes:
            ...

    class Out:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            ...

        def encode(self) -> bytes:
            ...

        def decode(self, *args: Any, **kwargs: Any) -> None:
            ...

        @property
        def packed(self) -> bytes:
            ...


class ProtoModule:
    PMODNAME: str

    class Stream:
        def recv(self, segment: bytes) -> List[Union[bytes, str]]:
            ...

        def close(self) -> bytes:
            ...

    @staticmethod
    def enframe(buffer: bytes, imei: Optional[str] = None) -> bytes:
        ...

    class DecodeError(Exception):
        ...

    @staticmethod
    def exposed_protos() -> List[Tuple[str, bool]]:
        ...

    @staticmethod
    def probe_buffer(buffer: bytes) -> bool:
        ...

    @staticmethod
    def parse_message(packet: bytes, is_incoming: bool = True) -> Any:
        ...

    @staticmethod
    def inline_response(packet: bytes) -> Optional[bytes]:
        ...

    @staticmethod
    def is_goodbye_packet(packet: bytes) -> bool:
        ...

    @staticmethod
    def imei_from_packet(packet: bytes) -> Optional[str]:
        ...

    @staticmethod
    def proto_of_message(packet: bytes) -> str:
        ...

    @staticmethod
    def proto_handled(proto: str) -> bool:
        ...

    @staticmethod
    def class_by_prefix(prefix: str) -> Union[Type[ProtoClass], List[str]]:
        ...

    @staticmethod
    def make_response(
        cmd: str, imei: str, **kwargs: Any
    ) -> Optional[ProtoClass.Out]:
        ...
