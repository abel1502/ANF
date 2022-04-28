import typing
import abc
import asyncio
import enum as py_enum

from .ipacket import T, U
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *
from .struct import *
from .misc import *


class Dynamic(IPacket[T]):
    def __init__(self, packet: CtxParam[IPacket[T]]):
        self._packet = packet

    # TODO: Maybe not public?
    def get_packet(self, ctx: Context,
                   exc: typing.Type[Exception] | Exception | None = None) -> IPacket[T]:
        try:
            return eval_ctx_param(self._packet, ctx)
        except KeyError as e:
            if exc is None:
                raise

            raise exc from e

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        return await self.get_packet(ctx, PacketEncodeError) \
            .encode(stream, obj, ctx)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        return await self.get_packet(ctx, PacketDecodeError) \
            .decode(stream, ctx)

    def _sizeof(self, ctx: Context) -> int:
        return self.get_packet(ctx, NotSizeableError) \
            .sizeof(ctx)

    # TODO: Delayed _postpone as well?


class Conditional(Dynamic[T | U], typing.Generic[T, U]):
    def __init__(self, cond: CtxParam[bool],
                 case_true: IPacket[T], case_false: IPacket[U] = NoOpPacket):
        def get_packet(ctx: Context) -> IPacket[T | U]:
            result = eval_ctx_param(cond, ctx)
            ctx.set_md("cond", result)
            return case_true if result else case_false

        Dynamic.__init__(self, get_packet)


# TODO: Somehow account for the generic?
class Discriminated(StructAdapter[typing.Tuple[int | IPacket, typing.Any]]):
    def __init__(self, type_field: IPacket[int], cases: typing.Mapping[int, IPacket]):
        super().__init__(Struct(
            # TODO: Perhaps go back to using Mapping, but it seems troublesome
            "type" / type_field,
            "value" / Dynamic(lambda ctx: cases[ctx.parent.type.value]),
        ), master_field="value")

    def _modify_enc(self, obj: typing.Tuple[int | IPacket, typing.Any], ctx: Context) -> _StructDict:
        if not isinstance(obj, tuple) or len(obj) != 2:
            raise PacketObjTypeError(obj, tuple)

        return dict(type=obj[0], value=obj[1])

    def _modify_dec(self, obj: _StructDict, ctx: Context) -> T:
        return (obj["type"], obj["value"])


__all__ = (
    "Dynamic",
    "Conditional",
    "Discriminated",
)
