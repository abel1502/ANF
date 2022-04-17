import typing
import abc
import asyncio

from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *


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


class Byte(BytesPacket):
    def __init__(self):
        super().__init__(1)

    # TODO: Special __repr__


Byte: Byte = Byte()


__all__ = (
    "BytesPacket",
    "Byte",
)
