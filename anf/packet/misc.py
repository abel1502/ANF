import typing
import abc
import asyncio

from .ipacket import T
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *
from .struct import *


@IPacket.singleton
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


NoOpPacket: NoOpPacket


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


class Padded(StructAdapter[T]):
    def __init__(self, wrapped: IPacket[T], size: CtxParam[int]):
        super().__init__(Struct(
            "data" / wrapped,
            "pad_size" / Virtual(lambda ctx: self.sizeof(ctx.parent) - len(ctx.parent.data.encoded)),
            "padding" / Padding(this.pad_size),
        ))

        self._size: CtxParam[int] = size

    def _sizeof(self, ctx: Context) -> int:
        return eval_ctx_param(self._size, ctx)


class Aligned(StructAdapter[T]):
    def __init__(self, wrapped: IPacket[T], alignment: CtxParam[int]):
        super().__init__(Struct(
            "data" / wrapped,
            "pad_size" / Virtual(lambda ctx: (-len(ctx.parent.data.encoded)) % self._get_alignment(ctx.parent)),
            "padding" / Padding(this.pad_size),
        ))

        self._alignment: CtxParam[int] = alignment

    def _get_alignment(self, ctx: Context) -> int:
        return eval_ctx_param(self._alignment, ctx)


class AutoPacket(PacketAdapter[T, T | None]):
    """
    A special packet that computes its value automatically
    """

    def __init__(self, wrapped: IPacket[T], value: CtxParam[T],
                 validate_enc: bool, validate_dec: bool,
                 override_enc: bool = False, postpone_dec: bool = False):
        """
        :param wrapped: The underlying packet
        :param value: The deduced value (optionally context-dependent)
        :param validate_enc: Whether to check the explicitly given value
            against the deduced one upon encoding the packet
        :param validate_dec: Whether to check the received value
            against the deduced one upon decoding the packet
        :param override_enc: Whether to allow the user to override the
            value being encoded with their own. Requires `not validate_enc`
        :param postpone_dec: Whether to postpone the decoding check
            until the end of parent container parsing. Requires `validate_dec`.
            This is set automatically upon postponing the packet.
            Note that wrapping this packet in a StructAdapter may unintentionally
            change the moment when the validation is carried out, as well as
            the context it is evaluated in
        """

        super().__init__(wrapped)
        self._value: CtxParam[typing.Any] = value
        self._validate_enc = validate_enc
        self._override_enc = override_enc
        self._validate_dec = validate_dec
        self._postpone_dec = postpone_dec

    def _get_value(self, ctx: Context) -> T:
        return eval_ctx_param(self._value, ctx)

    def _modify_enc(self, obj: T | None, ctx: Context) -> T:
        value = self._get_value(ctx)

        if self._validate_enc and obj is not None and obj != value:
            PacketObjTypeError.validate(obj, type(value))

            raise PacketEncodeError("Explicitly specified value for automatic field is invalid.")

        if self._override_enc and obj is not None:
            value = obj

        ctx.register_val(value)

        return value

    def _modify_dec(self, obj: T, ctx: Context) -> T:
        if self._validate_dec:
            def validate():
                if self._get_value(ctx) != obj:
                    raise PacketDecodeError("Received value for automatic field is invalid.")

            if self._postpone_dec:
                on_finish: Event[[]] = ctx.parent.get_md("on_finish")
                assert isinstance(on_finish, Event)
                on_finish.add(validate)
            else:
                validate()

        return obj

    def _postpone(self, level: int) -> None:
        # TODO: Maybe not?
        self._postpone_dec = True


class Const(AutoPacket[T]):
    """
    A special packet that always contains the same value (possibly context-dependent),
    and validates in during encoding and decoding.

    Note: see the note for `postpone_dec` in AutoPacket.__init__
    """

    def __init__(self, value: CtxParam[T], wrapped: IPacket[T] | None = None):
        if wrapped is None:
            assert isinstance(value, bytes) or \
                   hasattr(value, "__call__"), "Const operates on bytes by default"

            from .bytestr import Bytes
            wrapped = Bytes(lambda ctx: len(eval_ctx_param(value, ctx)))

        super().__init__(wrapped, value, True, True)


class Default(AutoPacket[T]):
    def __init__(self, wrapped: IPacket[T], value: CtxParam[T]):
        super().__init__(wrapped, value, False, False, True)


class Deduced(AutoPacket[T]):
    def __init__(self, wrapped: IPacket[T], value: CtxParam[T]):
        super().__init__(wrapped, value, True, False)


class Check(PacketValidator[None]):
    """
    A special packet that doesn't encode or decode anything,
    but checks that a predicate is true upon encoding and decoding.
    Often demands being `postpone`d.
    """

    def __init__(self, predicate: CtxParam[bool]):
        super().__init__(NoOpPacket)
        self._pred = predicate

    def _validate(self, ctx: Context) -> bool:
        return eval_ctx_param(self._pred, ctx)


__all__ = (
    "NoOpPacket",
    "Padding",
    "Virtual",
    "Padded",
    "Aligned",
    "AutoPacket",
    "Const",
    "Default",
    "Deduced",
    "Check",
)

