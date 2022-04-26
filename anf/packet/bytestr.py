import typing
import abc
import asyncio
import codecs

from .ipacket import T
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *
from .tunneling import *
from .misc import *


class BytesPacket(IPacket[bytes]):
    def __init__(self, size: CtxParam[int]):
        self._size = size

    async def _encode(self, stream: IStream, obj: bytes, ctx: Context) -> None:
        PacketObjTypeError.validate(obj, bytes)

        if len(obj) != self.sizeof(ctx):
            raise PacketEncodeError("Wrong data length for BytesPacket")

        await stream.send(ctx.register_enc(obj))

    async def _decode(self, stream: IStream, ctx: Context) -> bytes:
        return ctx.register_enc(await stream.recv(self.sizeof(ctx)))

    def _sizeof(self, ctx: Context) -> int:
        return eval_ctx_param(self._size, ctx)


@IPacket.singleton
class GreedyBytesPacket(IPacket[bytes]):
    def __init__(self):
        pass

    async def _encode(self, stream: IStream, obj: bytes, ctx: Context) -> None:
        PacketObjTypeError.validate(obj, bytes)

        await stream.send(ctx.register_enc(obj))

    async def _decode(self, stream: IStream, ctx: Context) -> bytes:
        return ctx.register_enc(await stream.recv())


GreedyBytesPacket: GreedyBytesPacket


@IPacket.singleton
class Byte(BytesPacket):
    def __init__(self):
        super().__init__(1)

    # TODO: Special __repr__


Byte: Byte


class PaddedString(PacketAdapter[str, bytes]):
    def __init__(self, size: CtxParam[int], encoding: str = "utf-8"):
        super().__init__(PaddedPacket(BytesPacket(
            lambda ctx: eval_ctx_param(
                ctx.parent.get_md("expected_len", size), ctx
            )
        ), size))

        self._encoding: str = encoding

    def _modify_enc(self, obj: str, ctx: Context) -> bytes:
        PacketObjTypeError.validate(obj, str)

        obj = obj.rstrip("\0")
        ctx.register_val(obj)

        try:
            data: bytes = obj.encode(self._encoding)
        except (UnicodeError, LookupError) as e:
            raise PacketEncodeError from e

        ctx.set_md("expected_len", len(data))

        return data

    def _modify_dec(self, data: bytes, ctx: Context) -> str:
        try:
            obj: str = data.decode(self._encoding)
        except (UnicodeError, LookupError) as e:
            raise PacketDecodeError from e

        obj = obj.rstrip("\0")

        return obj


class CString(IPacket[str]):
    def __init__(self, encoding: str = "utf-8"):
        self._encoding: str = encoding

    async def _encode(self, stream: IStream, obj: str, ctx: Context) -> None:
        PacketObjTypeError.validate(obj, str)

        obj = obj.rstrip("\0")
        ctx.register_val(obj)
        obj += "\0"

        try:
            data: bytes = obj.encode(self._encoding)
        except (UnicodeError, LookupError) as e:
            raise PacketEncodeError from e

        ctx.register_enc(data)

        await stream.send(data)

    async def _decode(self, stream: IStream, ctx: Context) -> str:
        try:
            decoder = codecs.getincrementaldecoder(self._encoding)()
        except LookupError as e:
            raise PacketDecodeError from e

        result: typing.List[str] = []
        encoded = bytearray()

        try:
            while True:
                byte = await stream.recv(1)
                encoded += byte
                data = decoder.decode(byte)
                if data:
                    result.append(data)
                if data == "\0":
                    break
            result.append(decoder.decode(b''))
        except UnicodeError as e:
            raise PacketDecodeError from e

        ctx.register_enc(bytes(encoded))

        return "".join(result).rstrip("\0")


class GreedyStringPacket(PacketAdapter[str, bytes]):
    def __init__(self, encoding: str = "utf-8"):
        super().__init__(GreedyBytesPacket)

        self._encoding: str = encoding

    def _modify_enc(self, obj: str, ctx: Context) -> bytes:
        PacketObjTypeError.validate(obj, str)

        obj = obj.rstrip("\0")
        ctx.register_val(obj)

        try:
            data: bytes = obj.encode(self._encoding)
        except (UnicodeError, LookupError) as e:
            raise PacketEncodeError from e

        return data

    def _modify_dec(self, data: bytes, ctx: Context) -> str:
        try:
            obj: str = data.decode(self._encoding)
        except (UnicodeError, LookupError) as e:
            raise PacketDecodeError from e

        obj = obj.rstrip("\0")

        return obj


class PascalString(PacketWrapper[str]):
    def __init__(self, size_field: IPacket[int], encoding: str = "utf-8"):
        super().__init__(SizePrefixed(size_field, GreedyStringPacket(encoding)))



__all__ = (
    "BytesPacket",
    "GreedyBytesPacket",
    "Byte",
    "PaddedString",
    "CString",
    "GreedyStringPacket",
    "PascalString",
)
