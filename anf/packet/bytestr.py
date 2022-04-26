import typing
import abc
import asyncio

from .ipacket import T
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *
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

        if not obj.endswith("\0"):
            obj += "\0"

        try:
            data: bytes = obj.encode(self._encoding)
        except UnicodeError as e:
            raise PacketEncodeError from e

        ctx.set_md("expected_len", len(data))

        return data

    def _modify_dec(self, data: bytes, ctx: Context) -> str:
        try:
            obj: str = data.decode(self._encoding)
        except UnicodeError as e:
            raise PacketDecodeError from e

        obj = obj.rstrip("\0")

        return obj


__all__ = (
    "BytesPacket",
    "GreedyBytesPacket",
    "Byte",
    "PaddedString",
)
