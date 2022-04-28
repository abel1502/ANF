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
from .repeaters import Array


class Transformed(PacketWrapper[T]):
    def __init__(self, wrapped: IPacket[T],
                 dec_size: CtxParam[int] | None = None,
                 enc_size: CtxParam[int] | None = None,
                 dec_func: typing.Callable[[bytes], bytes] = lambda x: x,
                 enc_func: typing.Callable[[bytes], bytes] = lambda x: x):
        super().__init__(wrapped)
        self._dec_size: CtxParam[int] | None = dec_size
        self._enc_size: CtxParam[int] | None = enc_size
        self._dec_func: typing.Callable[[bytes], bytes] = dec_func
        self._enc_func: typing.Callable[[bytes], bytes] = enc_func

    def _get_dec_size(self, ctx: Context) -> int | None:
        dec_size = self._dec_size
        if dec_size is None:
            return None
        return eval_ctx_param(dec_size, ctx)

    def _get_enc_size(self, ctx: Context) -> int | None:
        enc_size = self._enc_size
        if enc_size is None:
            return None
        return eval_ctx_param(enc_size, ctx)

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        substream = BytesStream()

        await self.wrapped.encode(substream, obj, ctx)

        await stream.send(substream.get_data())

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        data: bytes = await stream.recv(self.sizeof(ctx))

        substream = BytesStream(data)

        return self.wrapped.decode(substream, ctx)

    def _sizeof(self, ctx: Context) -> int:
        dec_size = self._get_dec_size(ctx)
        enc_size = self._get_enc_size(ctx)

        cnt_nones = (dec_size is None) + (enc_size is None)

        sizeable: bool = (cnt_nones == 1) or \
                         (cnt_nones == 0 and dec_size == enc_size)

        if sizeable:
            return enc_size or dec_size

        # In case it was already encoded.
        # TODO: Maybe fail sometimes?
        return super()._sizeof(ctx)


ST = typing.TypeVar("ST", bound=typing.Sized)


class CountPrefixed(StructAdapter[ST], typing.Generic[ST]):
    def __init__(self, count_field: IPacket[int], data_field: typing.Callable[[CtxParam[int]], IPacket[ST]]):
        super().__init__(Struct(
            "count" / Deduced(count_field, lambda ctx: len(ctx.parent.data.value)),
            "data" / data_field(lambda ctx: ctx.parent.count.value)
        ))


class CountPrefixedArray(CountPrefixed[typing.List[T]], typing.Generic[T]):
    def __init__(self, count_field: IPacket[int], data_item_field: IPacket[T]):
        super().__init__(count_field, lambda cnt: data_item_field[cnt])


class SizePrefixed(StructAdapter[T]):
    def __init__(self, size_field: IPacket[int], data_field: IPacket[T]):
        super().__init__(Struct(
            "size" / postponed(Deduced(size_field, lambda ctx: len(ctx.parent.data.encoded))),
            "data" / data_field
        ))


class Checksum(PacketWrapper[T | None]):
    """
    A special packet that computes and validates a checksum automatically.
    Often demands being `postpone`d.

    Note: see the note for `postpone_dec` in AutoPacket.__init__
    """

    def __init__(self, wrapped: IPacket[T | None],
                 hash_func: typing.Callable[[bytes], T | None],
                 data: CtxParam[bytes], *,
                 validate: typing.Callable[[Context, T, T], bool] =
                 (lambda ctx, value, hashed: value == hashed),
                 compute: typing.Callable[[Context, T], bytes] =
                 (lambda ctx, hashed: hashed)):

        hashed = lambda ctx: hash_func(eval_ctx_param(data, ctx))

        super().__init__(Deduced(
            wrapped,
            lambda ctx: compute(ctx, hashed(ctx))
        ))

        self._validate_func = lambda ctx: validate(ctx, ctx.value, hashed(ctx))

        self._postpone_validation = False

    def _validate(self, ctx: Context, computed_here: bool = False) -> None:
        if not self._validate_func(ctx):
            PacketEncodeError("The computed hashsum didn't pass the validation somehow"
                              if computed_here else
                              "Wrong checksum")

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        await super()._encode(stream, obj, ctx)

        if self._postpone_validation:
            on_finish: Event[[]] = ctx.parent.get_md("on_finish")
            on_finish.add(lambda: self._validate(ctx, True))
        else:
            self._validate(ctx, True)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        result = await super()._decode(stream, ctx)

        if self._postpone_validation:
            on_finish: Event[[]] = ctx.parent.get_md("on_finish")
            on_finish.add(lambda: self._validate(ctx))
        else:
            ctx.register_val(result)  # So that it's immediately available
            self._validate(ctx)

        return result

    def _postpone(self, level: int) -> None:
        self._postpone_validation = True


__all__ = (
    "Transformed",
    "CountPrefixed",
    "CountPrefixedArray",
    "SizePrefixed",
    "Checksum",
)
