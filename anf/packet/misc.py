import typing
import abc
import asyncio

from .ipacket import T
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *
from .compound import *


class NoOpPacket(IPacket[None]):
    def __init__(self):
        pass

    async def _encode(self, stream: IStream, obj: None, ctx: Context) -> None:
        PacketObjTypeError.validate(obj, None)
        ctx.register_enc(b'')

    async def _decode(self, stream: IStream, ctx: Context) -> None:
        ctx.register_enc(b'')

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


class Virtual(IPacket[T]):
    """
    A special packet that doesn't affect the stream, but does compute and store some value.
    """

    def __init__(self, value: CtxParam[T]):
        self._value: CtxParam[typing.Any] = value

    def _get_value(self, ctx: Context) -> T:
        return eval_ctx_param(self._value, ctx)

    async def _encode(self, stream: IStream, obj: T | None, ctx: Context) -> None:
        value = self._get_value(ctx)
        ctx.register_val(value)  # To overwrite the user-specified one, if any

        if obj is not None and obj != value:
            PacketObjTypeError.validate(obj, type(value))
            raise PacketEncodeError("Explicitly specified value for computed field is wrong.")

        ctx.register_enc(b'')

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        ctx.register_enc(b'')
        return self._get_value(ctx)

    def _sizeof(self, ctx: Context) -> int:
        return 0


class AutoPacket(PacketAdapter[T, T | None]):
    """
    A special packet that computes its value automatically
    """

    def __init__(self, wrapped: IPacket[T], value: CtxParam[T],
                 validate_enc: bool, validate_dec: bool):
        super().__init__(wrapped)
        self._value: CtxParam[typing.Any] = value
        self._validate_enc = validate_enc
        self._validate_dec = validate_dec

    def _get_value(self, ctx: Context) -> T:
        return eval_ctx_param(self._value, ctx)

    def _modify_enc(self, obj: T | None, ctx: Context) -> T:
        value = self._get_value(ctx)

        if self._validate_enc and obj is not None and obj != value:
            PacketObjTypeError.validate(obj, type(value))

            raise PacketEncodeError("Explicitly specified value for automatic field is invalid.")

        return value

    def _modify_dec(self, obj: T, ctx: Context) -> T:
        if self._validate_dec and self._get_value(ctx) != obj:
            raise PacketDecodeError("Received value for automatic field is invalid.")

        return obj


class Const(AutoPacket[T]):
    def __init__(self, value: CtxParam[T], wrapped: IPacket[T] | None = None):
        if wrapped is None:
            assert isinstance(value, bytes) or \
                   hasattr(value, "__call__"), "Const operates on bytes by default"

            from .bytestr import BytesPacket
            wrapped = BytesPacket

        super().__init__(wrapped, value, True, True)


class Default(AutoPacket[T]):
    def __init__(self, wrapped: IPacket[T], value: CtxParam[T]):
        super().__init__(wrapped, value, False, False)


class Deduced(AutoPacket[T]):
    def __init__(self, wrapped: IPacket[T], value: CtxParam[T]):
        super().__init__(wrapped, value, True, False)


class PaddedPacket(PacketAdapter[T, typing.Dict[str, typing.Any]], typing.Generic[T]):
    def __init__(self, wrapped: IPacket[T], size: CtxParam[int]):
        super().__init__(Struct(
            "data" / wrapped,
            "pad_size" / Virtual(lambda ctx: self.sizeof(ctx.parent) - len(ctx.parent.data.encoded)),
            "padding" / Padding(this.pad_size),
        ))

        self._size = size

    def _modify_enc(self, obj: T, ctx: Context) -> typing.Dict[str, typing.Any]:
        return {"data": obj}

    def _modify_dec(self, obj: typing.Dict[str, typing.Any], ctx: Context) -> T:
        return obj["data"]

    def _sizeof(self, ctx: Context) -> int:
        return eval_ctx_param(self._size, ctx)


__all__ = (
    "NoOpPacket",
    "Padding",
    "PaddedPacket",
)
