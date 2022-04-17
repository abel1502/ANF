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
        self.data_field: typing.Callable[[int], IPacket[ST]] = \
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
        count_field = self.count_field
        count_ctx: Context = ctx.get_member(count_field.name)
        data_field = self.data_field(count_ctx.value)
        data_ctx: Context = ctx.get_member(data_field.name)

        return count_field.sizeof(count_ctx) + data_field.sizeof(data_ctx)


T = typing.TypeVar("T")


# TODO: Encapsulate in some sort of restreamed, perhaps?
class SizePrefixed(IPacket):
    def __init__(self, count_field: IPacket[int], data_field: IPacket[T]):
        self.size_field: IPacket[int] = RenamedPacket(count_field, "size")
        self.data_field: IPacket[T] = RenamedPacket(data_field, "data")

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        size_field = self.size_field
        data_field = self.data_field

        size_ctx = ctx.make_child(size_field.name)
        data_ctx = ctx.make_child(data_field.name)

        sub_stream = BytesStream()
        await data_field.encode(sub_stream, obj, data_ctx)

        enc = sub_stream.get_data()

        await size_field.encode(stream, len(enc), size_ctx)
        await stream.send(enc)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        size_field = self.size_field
        size_ctx = ctx.make_child(size_field.name)
        obj_size = await size_field.decode(stream, size_ctx)

        sub_stream = BytesStream(await stream.recv(obj_size))

        data_field = self.data_field
        data_ctx = ctx.make_child(data_field.name)
        obj: T = await data_field.decode(sub_stream, data_ctx)

        return obj

    def _sizeof(self, ctx: Context) -> int:
        size_field = self.size_field
        size_ctx: Context = ctx.get_member(size_field.name)

        return size_field.sizeof(size_ctx) + size_ctx.value


__all__ = (
    "Struct",
    "CountPrefixed",
    "SizePrefixed",
)
