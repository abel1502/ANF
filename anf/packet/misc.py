import typing
import abc
import asyncio

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


__all__ = (
    "NoOpPacket",
)
