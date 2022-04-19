import typing
import abc
import asyncio

from .ipacket import T
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *


class NoOpPacket(IPacket):
    def __init__(self):
        pass

    async def _encode(self, stream: IStream, obj: None, ctx: Context) -> None:
        PacketObjTypeError.validate(obj, None)

    async def _decode(self, stream: IStream, ctx: Context) -> None:
        pass

    def _sizeof(self, ctx: Context) -> int:
        return 0


NoOpPacket: NoOpPacket = NoOpPacket()


class Padding(IPacket):
    def __init__(self, size: CtxParam[int]):
        self._size: CtxParam[int] = size

    async def _encode(self, stream: IStream, obj: None, ctx: Context) -> None:
        PacketObjTypeError.validate(obj, None)

        sz = self.sizeof(ctx)
        if sz < 0:
            raise PacketEncodeError("Padding size cannot be negative")

        data: bytes = b"\0" * sz
        await stream.send(ctx.register_enc(data))

    async def _decode(self, stream: IStream, ctx: Context) -> None:
        sz = self.sizeof(ctx)
        assert sz >= 0
        ctx.register_enc(await stream.recv(sz))

    def _sizeof(self, ctx: Context) -> int:
        return eval_ctx_param(self._size, ctx)


class PaddedPacket(PacketWrapper[T]):
    def __init__(self, wrapped: IPacket[T], size: CtxParam[int]):
        super().__init__(wrapped)

        self._size = size

    def _get_padding(self, ctx: Context) -> Padding:
        sz = self.sizeof(ctx) - self.wrapped.sizeof(ctx)
        return Padding(sz)

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        await super()._encode(stream, obj, ctx)
        enc = ctx.encoded
        await self._get_padding(ctx).encode(stream, None, ctx)
        enc += ctx.encoded
        ctx.register_enc(enc)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        obj = await super()._decode(stream, ctx)
        enc = ctx.encoded
        await self._get_padding(ctx).decode(stream, ctx)
        enc += ctx.encoded
        ctx.register_enc(enc)

        return obj

    def _sizeof(self, ctx: Context) -> int:
        return eval_ctx_param(self._size, ctx)


__all__ = (
    "NoOpPacket",
    "Padding",
    "PaddedPacket",
)
