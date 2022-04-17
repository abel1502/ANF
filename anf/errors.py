import typing


#################
# Stream errors #
#################

class StreamOpenError(Exception):
    pass


class StreamReadError(Exception):
    pass


class StreamWriteError(Exception):
    pass


#################
# Packet errors #
#################

class PacketInvalidError(Exception):
    pass


class PacketEncodeError(PacketInvalidError):
    pass


class PacketObjTypeError(PacketEncodeError):
    def __init__(self, obj: typing.Any, expected: typing.Tuple[typing.Type] | typing.Type):
        super().__init__(f"Wrong packet obj type: got {type(obj)}, expected {expected}")

    @classmethod
    def validate(cls, obj: typing.Any, expected: typing.Tuple[typing.Type] | typing.Type | None):
        if expected is None:
            expected = type(None)

        if not isinstance(obj, expected):
            raise cls(obj, expected)


class PacketDecodeError(PacketInvalidError):
    pass


class NotSizeableError(Exception):
    pass


