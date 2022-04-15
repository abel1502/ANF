import typing
import abc
import struct
import asyncio
import itertools

from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *


PyStructType: typing.TypeAlias = bool | int | float


class PyStructPacket(IPacket[PyStructType]):
    def __init__(self, fmt: str, endianness: str = "!"):
        assert fmt in "bB?hHiIlLqQnNefd"
        assert endianness in "@=<>!"

        self._struct: struct.Struct = struct.Struct(endianness + fmt)

    async def _encode(self, stream: IStream, obj: PyStructType, ctx: Context) -> None:
        try:
            data: bytes = ctx.register_enc(self._struct.pack(obj))
        except struct.error as e:
            raise PacketEncodeError() from e

        await stream.send(data)

    async def _decode(self, stream: IStream, ctx: Context) -> PyStructType:
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


class BytesIntPacket(IPacket[int]):
    def __init__(self, size: int, signed: bool, endianness: typing.Literal["!", "<", ">"] = "!"):
        assert endianness in "!><"

        self._size: int = size
        self._signed: bool = signed
        self._endianness: typing.Literal["little", "big"] = \
            typing.cast(typing.Literal["little", "big"], "little" if endianness == "<" else "big")

    async def _encode(self, stream: IStream, obj: int, ctx: Context) -> None:
        try:
            data: bytes = ctx.register_enc(obj.to_bytes(
                self._size, self._endianness, signed=self._signed
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
        return self._size

    def __repr__(self) -> str:
        return f"{type(self).__name__}(sz={self._size}, signed={self._signed}, order={self._endianness})"


class VarInt(IPacket):
    def __init__(self):
        pass

    async def _encode(self, stream: IStream, obj: int, ctx: Context) -> None:
        data = bytearray()

        if obj < 0:
            raise PacketEncodeError("VarInt cannot encode negative numbers")

        while obj >= 0x80:
            data.append((obj & 0x7f) | 0x80)
        assert obj < 0x80
        data.append(obj)

        data = ctx.register_enc(bytes(data))

        await stream.send(data)

    async def _decode(self, stream: IStream, ctx: Context) -> int:
        data = bytearray()
        num = 0
        seen_end = False
        while not seen_end:
            byte = (await stream.recv(1))[0]
            seen_end = byte & 0x80
            data.append(byte)
            num = (num << 7) | (byte & 0x7f)

        return num

    def __repr__(self) -> str:
        return f"{type(self).__name__}"


VarInt = VarInt()
VarInt.__call__ = lambda self: self


class ZigZag(IPacket):
    def __init__(self):
        pass

    async def _encode(self, stream: IStream, obj: int, ctx: Context) -> None:
        obj <<= 1
        if obj < 0:
            obj = ~obj

        await VarInt.encode(stream, obj, ctx)

    async def _decode(self, stream: IStream, ctx: Context) -> int:
        obj = await VarInt.decode(stream, ctx)

        if obj & 1:
            obj = ~obj
        obj >>= 1

        return obj

    def __repr__(self) -> str:
        return f"{type(self).__name__}"


ZigZag = ZigZag()
ZigZag.__call__ = lambda self: self


def _create_int_types() -> typing.Dict[str, PyStructPacket]:
    _sz_to_struct = {8: "b", 16: "h", 32: "i", 64: "l"}
    _endian_to_struct = {"l": "<", "b": ">", "": "!"}  # Default is network, i.e. big

    result = {}

    for size, signed, endian in itertools.product((8, 16, 32, 64), (False, True), ("l", "b", "")):
        fmt = _sz_to_struct[size]
        if not signed:
            fmt = fmt.upper()

        name = "{signed}Int{size}{endian}".format(
            signed="" if signed else "U", size=size, endian=endian
        )

        integral_type = PyStructPacket(fmt, _endian_to_struct[endian])
        integral_type.__repr__ = lambda self: f"{type(self).__name__}"
        integral_type.__call__ = lambda self: self

        result[name] = integral_type

    result["_all_int_types"] = tuple(result.keys())

    return result


locals().update(_create_int_types())

# Type hints for the above code
Int8l:   PyStructPacket
Int8b:   PyStructPacket
Int8:    PyStructPacket
UInt8l:  PyStructPacket
UInt8b:  PyStructPacket
UInt8:   PyStructPacket
Int16l:  PyStructPacket
Int16b:  PyStructPacket
Int16:   PyStructPacket
UInt16l: PyStructPacket
UInt16b: PyStructPacket
UInt16:  PyStructPacket
Int32l:  PyStructPacket
Int32b:  PyStructPacket
Int32:   PyStructPacket
UInt32l: PyStructPacket
UInt32b: PyStructPacket
UInt32:  PyStructPacket
Int64l:  PyStructPacket
Int64b:  PyStructPacket
Int64:   PyStructPacket
UInt64l: PyStructPacket
UInt64b: PyStructPacket
UInt64:  PyStructPacket


__all__ = ("PyStructPacket", *_all_int_types)
