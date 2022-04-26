import typing
import abc
import struct
import asyncio
import itertools

from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *


# PyStructType: typing.TypeAlias = bool | int | float
IntegralT = typing.TypeVar("IntegralT", bool, int, float)


class PyStruct(IPacket[IntegralT]):
    def __init__(self, fmt: str, endianness: str = "!"):
        assert fmt in "bB?hHiIlLqQnNefd"
        assert endianness in "@=<>!"

        self._struct: struct.Struct = struct.Struct(endianness + fmt)
        self._expected_type: typing.Type = \
            int if fmt in "bBhHiIlLqQnN" else \
            float if fmt in "efd" else \
            bool

    async def _encode(self, stream: IStream, obj: IntegralT, ctx: Context) -> None:
        PacketObjTypeError.validate(obj, self._expected_type)

        try:
            data: bytes = ctx.register_enc(self._struct.pack(obj))
        except struct.error as e:
            raise PacketEncodeError() from e

        await stream.send(data)

    async def _decode(self, stream: IStream, ctx: Context) -> IntegralT:
        data = ctx.register_enc(await stream.recv(self.sizeof(ctx)))

        try:
            obj = self._struct.unpack(data)
        except struct.error as e:
            raise PacketEncodeError() from e

        assert len(obj) == 1
        obj = obj[0]

        return obj

    def _sizeof(self, ctx: Context) -> int:
        return self._struct.size

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._struct.format})"


class BytesInt(IPacket[int]):
    def __init__(self, size: CtxParam[int], signed: bool, endianness: typing.Literal["!", "<", ">"] = "!"):
        assert endianness in "!><"

        self._size: CtxParam[int] = size
        self._signed: bool = signed
        self._endianness: typing.Literal["little", "big"] = \
            typing.cast(typing.Literal["little", "big"], "little" if endianness == "<" else "big")

    async def _encode(self, stream: IStream, obj: int, ctx: Context) -> None:
        PacketObjTypeError.validate(obj, int)

        try:
            data: bytes = ctx.register_enc(obj.to_bytes(
                self.sizeof(ctx), self._endianness, signed=self._signed
            ))
        except struct.error as e:
            raise PacketEncodeError() from e

        await stream.send(data)

    async def _decode(self, stream: IStream, ctx: Context) -> int:
        data = ctx.register_enc(await stream.recv(self.sizeof(ctx)))

        try:
            obj: int = int.from_bytes(
                data, self._endianness, signed=self._signed
            )
        except struct.error as e:
            raise PacketEncodeError() from e

        return obj

    def _sizeof(self, ctx: Context) -> int:
        return eval_ctx_param(self._size, ctx)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(sz={self._size}, signed={self._signed}, order={self._endianness})"


@IPacket.singleton
class VarInt(IPacket[int]):
    def __init__(self):
        pass

    async def _encode(self, stream: IStream, obj: int, ctx: Context) -> None:
        PacketObjTypeError.validate(obj, int)

        data = bytearray()

        if obj < 0:
            raise PacketEncodeError("VarInt cannot encode negative numbers")

        while obj >= 0x80:
            data.append((obj & 0x7f) | 0x80)
            obj >>= 7
        assert obj < 0x80
        data.append(obj)

        data = ctx.register_enc(bytes(data))

        await stream.send(data)

    async def _decode(self, stream: IStream, ctx: Context) -> int:
        data = bytearray()
        seen_end = False
        while not seen_end:
            byte = (await stream.recv(1))[0]
            seen_end = not (byte & 0x80)
            data.append(byte)

        ctx.register_enc(bytes(data))

        num = 0
        for byte in reversed(data):
            num = (num << 7) | (byte & 0x7f)

        return num

    def __repr__(self) -> str:
        return f"{type(self).__name__}"


VarInt: VarInt


@IPacket.singleton
class ZigZag(PacketAdapter[int, int]):
    def __init__(self):
        super().__init__(VarInt)

    def _modify_enc(self, obj: int, ctx: Context) -> int:
        obj <<= 1
        if obj < 0:
            obj = ~obj

        return obj

    def _modify_dec(self, obj: int, ctx: Context) -> int:
        if obj & 1:
            obj = ~obj
        obj >>= 1

        return obj

    def __repr__(self) -> str:
        return f"{type(self).__name__}"


ZigZag: ZigZag


def _create_int_types() -> typing.Dict[str, PyStruct[int] | typing.Tuple[str, ...]]:
    _sz_to_struct = {8: "b", 16: "h", 32: "i", 64: "q"}
    _endian_to_struct = {"l": "<", "b": ">", "": "!"}  # Default is network, i.e. big

    result = {}

    for size, signed, endian in itertools.product((8, 16, 32, 64), (False, True), ("l", "b", "")):
        fmt = _sz_to_struct[size]
        if not signed:
            fmt = fmt.upper()

        name = "{signed}Int{size}{endian}".format(
            signed="" if signed else "U", size=size, endian=endian
        )

        integral_type = PyStruct(fmt, _endian_to_struct[endian])
        integral_type.__repr__ = lambda self: f"{type(self).__name__}"
        integral_type.__call__ = lambda self: self

        result[name] = integral_type

    result["_all_int_types"] = tuple(result.keys())

    return result


globals().update(_create_int_types())


Half = PyStruct("e")
Float = PyStruct("f")
Double = PyStruct("d")


# Type hints for the above code
Int8l:   PyStruct[int]
Int8b:   PyStruct[int]
Int8:    PyStruct[int]
UInt8l:  PyStruct[int]
UInt8b:  PyStruct[int]
UInt8:   PyStruct[int]
Int16l:  PyStruct[int]
Int16b:  PyStruct[int]
Int16:   PyStruct[int]
UInt16l: PyStruct[int]
UInt16b: PyStruct[int]
UInt16:  PyStruct[int]
Int32l:  PyStruct[int]
Int32b:  PyStruct[int]
Int32:   PyStruct[int]
UInt32l: PyStruct[int]
UInt32b: PyStruct[int]
UInt32:  PyStruct[int]
Int64l:  PyStruct[int]
Int64b:  PyStruct[int]
Int64:   PyStruct[int]
UInt64l: PyStruct[int]
UInt64b: PyStruct[int]
UInt64:  PyStruct[int]

Half:   PyStruct[float]
Float:  PyStruct[float]
Double: PyStruct[float]

# (These are singletons, and this is here to help PyCharm understand it)
# VarInt: type(VarInt)
# ZigZag: type(ZigZag)


__all__ = (
    "PyStruct",
    "BytesInt",
    *_all_int_types,
    "VarInt", "ZigZag",
    "Half", "Float", "Double",
)
