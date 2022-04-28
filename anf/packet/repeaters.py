import typing
import abc
import asyncio

from .ipacket import T, U
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *
from .struct import *
from .misc import *


def _preprocess_seq(seq: typing.Sequence[T], exp_sz: int) -> typing.List[T | None]:
    PacketObjTypeError.validate(seq, typing.Sequence)

    if len(seq) > exp_sz:
        raise PacketEncodeError("Obj contains extra fields")

    if len(seq) < exp_sz:
        seq = list(seq)
        seq.extend([None] * (exp_sz - len(seq)))

    assert len(seq) == exp_sz

    return seq


class Array(IPacket[typing.List[T]]):
    def __init__(self, item: IPacket[T], count: CtxParam[int]):
        self._item: IPacket[T] = item
        self._count: CtxParam[int] = count

    def _get_count(self, ctx: Context) -> int:
        return eval_ctx_param(self._count, ctx)

    def _gen_sequence(self, ctx: Context) -> Sequence:
        # Intentionally done this way, to save space
        items = (self._item,) * self._get_count(ctx)
        return Sequence(*items)

    async def _encode(self, stream: IStream, obj: typing.Sequence[T], ctx: Context) -> None:
        sequence: Sequence[T] = self._gen_sequence(ctx)
        obj = _preprocess_seq(obj, len(sequence.fields))
        sequence: IPacket[typing.List[T]]

        return await sequence._encode(stream, obj, ctx)

    async def _decode(self, stream: IStream, ctx: Context) -> typing.List[T]:
        sequence: IPacket[typing.List[T]] = self._gen_sequence(ctx)

        return await sequence._decode(stream, ctx)

    def _sizeof(self, ctx: Context) -> int:
        try:
            item_size = self._item.sizeof()  # No context intentionally
        except NotSizeableError:
            return super().sizeof(ctx)

        return item_size * self._get_count(ctx)


# class GreedyRange(IPacket[typing.List[T]]):
#     def __init__(self, item: IPacket[T]):
#         self._item: IPacket[T] = item
#
#     async def _encode(self, stream: IStream, obj: typing.Sequence[T], ctx: Context) -> None:
#         obj = _preprocess_seq(obj, len(obj))
#
#         arr: IPacket[typing.List[T]] = Array[T](self._item, len(obj))
#
#         return await arr._encode(stream, obj, ctx)
#
#     async def _decode(self, stream: IStream, ctx: Context) -> typing.List[T]:
#         data: bytes = await stream.recv()
#         stream = BytesStream(data)
#         result: typing.List[T] = []
#
#         # TODO: Rework for a wrapper around Array with StopIf inside?
#         #       Or manually account for encoded, on_finish and enc_partial
#
#         while not stream.at_eof():
#             result.append(await self._item.decode(stream, ctx.make_child(None)))
#
#         return result


__all__ = (
    "Array",
    # "GreedyRange",
)
