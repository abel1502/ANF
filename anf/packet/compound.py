import typing
import abc
import asyncio
import warnings

from .ipacket import T
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *
from .struct import *
from .misc import *


ST = typing.TypeVar("ST", bound=typing.Sized)


class CountPrefixed(StructAdapter[ST]):
    def __init__(self, count_field: IPacket[int], data_field: typing.Callable[[CtxParam[int]], IPacket[ST]]):
        super().__init__(Struct(
            "count" / Deduced(count_field, lambda ctx: len(ctx.parent.data.value)),
            "data" / data_field(lambda ctx: ctx.parent.count.value)
        ))


# TODO: Encapsulate in some sort of restreamed, perhaps?
class SizePrefixed(IPacket[T]):
    def __init__(self, count_field: IPacket[int], data_field: IPacket[T]):
        self.size_field: IPacket[int] = count_field.renamed("size")
        self.data_field: IPacket[T] = data_field.renamed("data")

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
    "CountPrefixed",
    "SizePrefixed",
)
