import typing
import abc
import asyncio

from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *


class Struct(IPacket):
    pass


ST = typing.TypeVar("ST", bound=typing.Sized)


class CountPrefixed(IPacket[ST]):
    def __init__(self, count_field: IPacket[int], data_field: typing.Callable[[int], IPacket[ST]]):
        self.count_field: IPacket[int] = RenamedPacket(count_field, "count")
        self.data_field: typing.Callable[[int], IPacket] = \
            lambda length: RenamedPacket(data_field(length), "data")

    async def _encode(self, stream: IStream, obj: ST, ctx: Context) -> None:
        obj_len = len(obj)
        count_field = self.count_field
        data_field = self.data_field(obj_len)

        count_ctx = ctx.make_child(count_field.name)
        data_ctx = ctx.make_child(data_field.name)

        await count_field.encode(stream, obj_len, count_ctx)
        await data_field.encode(stream, obj, data_ctx)

    async def _decode(self, stream: IStream, ctx: Context) -> ST:
        count_field = self.count_field
        count_ctx = ctx.make_child(count_field.name)
        obj_len = await count_field.decode(stream, count_ctx)

        data_field = self.data_field(obj_len)
        data_ctx = ctx.make_child(data_field.name)
        obj: ST = await data_field.decode(stream, data_ctx)

        if len(obj) != obj_len:
            raise PacketEncodeError("Unexpected data length")

        return obj

    def _sizeof(self, ctx: Context) -> int:
        count_ctx: Context = ctx.get_member(self.count_field.name)
        data_ctx: Context = ctx.get_member(self.data_field.name)

        return self.count_field.sizeof(count_ctx) + \
            self.data_field(count_ctx.value).sizeof(data_ctx)


__all__ = (
    "Struct",
    "CountPrefixed"
)
