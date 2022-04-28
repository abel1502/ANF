import asyncio
import typing
import abc
import io

from ..stream import *
from ..errors import *
from .context import *

if typing.TYPE_CHECKING:
    from .repeaters import Array


T = typing.TypeVar("T")
U = typing.TypeVar("U")


class IPacket(abc.ABC, typing.Generic[T]):
    """
    The base interface for a packet

    Other requirements:
     - Must be default-constructible, which would correspond to an empty packet
    """

    _MSG_WRONG_ASYNC = "{0}() is to be used with asynchronous streams. For a synchronous alternative, see {0}_sync()"

    ####################
    # Public interface #
    ####################

    async def encode(self, stream: IStream, obj: T, ctx: Context | None = None) -> None:
        """
        Encodes the packet asynchronously.

        :param stream: The asynchronous stream to encode to
        :param obj: The object to encode
        :param ctx: The current context, if present

        :raises StreamWriteError: if writing to the stream fails
        :raises PacketEncodeError: upon errors specific to encoding the packet
            (not network-related ones)
        """

        assert isinstance(stream, IStream), self._MSG_WRONG_ASYNC.format("encode")

        if ctx is None:
            ctx = Context()

        ctx.register_val(obj)

        return await self._encode(stream, obj, ctx)

    async def decode(self, stream: IStream, ctx: Context | None = None) -> T:
        """
        Decodes the packet asynchronously.

        :param stream: The asynchronous stream to decode from
        :param ctx: The current context, if present
        :return: The decoded object

        :raises StreamReadError: if reading from the stream fails
        :raises PacketDecodeError: upon errors specific to encoding the packet
            (not network-related ones)
        """

        assert isinstance(stream, IStream), self._MSG_WRONG_ASYNC.format("decode")

        if ctx is None:
            ctx = Context()

        return ctx.register_val(await self._decode(stream, ctx))

    async def encode_bytes(self, obj: T, ctx: Context | None = None) -> bytes:
        """
        Encodes the packet asynchronously and returns the resulting bytes.
        Arguments and exceptions are the same as for `encode`
        """

        stream = BytesStream()
        await self.encode(stream, obj, ctx)
        return stream.get_data()

    async def decode_bytes(self, data: bytes, ctx: Context | None = None,
                           completely: bool = True) -> T:
        """
        Decodes the packet asynchronously from the given bytes.
        Arguments and exceptions are the same as for `decode`
        """

        stream = BytesStream(data)
        result: T = await self.decode(stream, ctx)

        if completely and not stream.at_eof():
            raise PacketDecodeError("Unexpected trailing bytes remaining")

        return result

    @typing.overload
    def encode_sync(self, stream: typing.BinaryIO, obj: T) -> None:
        """
        Encodes the packet synchronously

        :param stream: The synchronous stream to encode to
        :param obj: The object to encode
        """

        ...

    @typing.overload
    def encode_sync(self, obj: T) -> bytes:
        """
        Encodes the packet synchronously

        :param obj: The object to encode
        :return: Encoded bytes
        """

        ...

    def encode_sync(self, *args):
        if len(args) == 1:
            obj = args[0]
            coro = self.encode_bytes(obj)
        elif len(args) == 2:
            stream, obj = args
            stream = SyncStream.create_from(stream)
            coro = self.encode_bytes(stream, obj)
        else:
            assert False, "Unknown overload"

        return asyncio.get_event_loop().run_until_complete(coro)

    def decode_sync(self, stream: typing.BinaryIO | bytes, completely: bool = False) -> T:
        """
        Decodes the packet synchronously

        :param stream: The synchronous stream or a byte sequence to decode from
        :param completely: Whether to expect the stream to be drained after the decoding
        :return: The decoded object
        """

        is_bytes: bool = False
        sync_stream: SyncStream | None = None

        if isinstance(stream, (bytes, bytearray, memoryview)):
            coro = self.decode_bytes(stream, completely=completely)
            is_bytes = True
        else:
            sync_stream = SyncStream.create_from(stream)
            coro = self.decode(sync_stream)

        data = asyncio.get_event_loop().run_until_complete(coro)

        # For bytes, this is already handled inside
        if not is_bytes and completely and not sync_stream.at_eof():
            raise PacketDecodeError("Unexpected trailing bytes remaining")

        return data

    def sizeof(self, ctx: Context | None = None) -> int:
        """
        Returns the size of the struct, if it is constant-size.

        :param ctx: The current context, if present
        :raises errors.NotSizeableError: if the packet's size depends on its contents
        """

        if ctx is None:
            ctx = Context()

        # TODO: Catch KeyError's and transform them to NotSizeableError
        return self._sizeof(ctx)

    def renamed(self, name: str) -> "Renamed":
        return Renamed.create(self, name=name)

    def postponed(self, level: int = 1) -> "Renamed":
        self._postpone(level=level)
        return Renamed.create(self, postpone_level=level)

    @property
    def name(self) -> str | None:
        return None

    @property
    def postpone_level(self) -> int:
        return 0

    def __rtruediv__(self, other: str) -> "Renamed":
        if not isinstance(other, str):
            return NotImplemented
        return self.renamed(other)

    def __getitem__(self, cnt: CtxParam[int]) -> "Array[T]":
        from .repeaters import Array

        return Array[T](self, cnt)

    def __repr__(self):
        return f"{type(self).__name__}"  # TODO: Elaborate?

    @staticmethod
    def singleton(cls: typing.Type[U]) -> U:
        return cls()

    ########################
    # Overrideable methods #
    ########################

    @abc.abstractmethod
    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        pass

    @abc.abstractmethod
    async def _decode(self, stream: IStream, ctx: Context) -> T:
        pass

    # @abc.abstractmethod
    def _sizeof(self, ctx: Context) -> int:
        try:
            return len(ctx.encoded)
        except KeyError:
            raise NotSizeableError("Packet wasn't yet encoded, and size cannot be determined")

    # @abc.abstractmethod
    def _postpone(self, level: int) -> None:
        pass


class PacketWrapper(IPacket[T]):
    def __init__(self, wrapped: IPacket[T]):
        self.wrapped: IPacket = wrapped

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        return await self.wrapped._encode(stream, obj, ctx)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        return await self.wrapped._decode(stream, ctx)

    def _sizeof(self, ctx: Context) -> int:
        return self.wrapped._sizeof(ctx)

    @property
    def name(self) -> str | None:
        return self.wrapped.name

    @property
    def postpone_level(self) -> int:
        return self.wrapped.postpone_level

    def __repr__(self):
        return repr(self.wrapped)

    def _postpone(self, level: int) -> None:
        self.wrapped._postpone(level)


class PacketValidator(PacketWrapper[T]):
    def __init__(self, wrapped: IPacket[T]):
        super().__init__(wrapped)

        self._postpone_validation = False

    def validate(self, ctx: Context) -> None:
        if not self._validate(ctx):
            raise PacketInvalidError("Validation failed")

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        # TODO: Revert for encode?
        if not self._postpone_validation:
            self.validate(ctx)
        else:
            on_finish: Event[[]] = ctx.parent.get_md("on_finish")
            assert on_finish is not None
            on_finish.add(lambda: self.validate(ctx))

        return await self.wrapped._encode(stream, obj, ctx)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        obj: T = await self.wrapped._decode(stream, ctx)

        if not self._postpone_validation:
            self.validate(ctx)
        else:
            ctx.register_val(obj)  # So it is already there for the validation
            on_finish: Event[[]] = ctx.parent.get_md("on_finish")
            assert on_finish is not None
            on_finish.add(lambda: self.validate(ctx))

        return obj

    def _postpone(self, level: int) -> None:
        self._postpone_validation = True

    @abc.abstractmethod
    def _validate(self, ctx: Context) -> bool:
        pass


class PacketAdapter(PacketWrapper[T], typing.Generic[T, U]):
    def __init__(self, wrapped: IPacket[T]):
        super().__init__(wrapped)

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        return await self.wrapped._encode(stream, self._modify_enc(obj, ctx), ctx)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        return self._modify_dec(await self.wrapped._decode(stream, ctx), ctx)

    @abc.abstractmethod
    def _modify_enc(self, obj: T, ctx: Context) -> U:
        pass

    @abc.abstractmethod
    def _modify_dec(self, obj: U, ctx: Context) -> T:
        pass


class Renamed(PacketWrapper):
    def __init__(self, wrapped: IPacket):
        super().__init__(wrapped)

        self._name: str | None = None
        self._postpone_level: int = 0

    @staticmethod
    def create(wrapped: IPacket,
               name: str | None = None,
               postpone_level: int | None = None) -> "Renamed":
        if not isinstance(wrapped, Renamed):
            return Renamed.create(Renamed(wrapped), name=name, postpone_level=postpone_level)

        if name is not None:
            wrapped._name = name
        if postpone_level is not None:
            wrapped._postpone_level = postpone_level

        return wrapped

    # TODO: Maybe instead demand that Renamed is the top-level wrapper?

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def postpone_level(self) -> int:
        return self._postpone_level


def postponed(wrapped: IPacket, level: int = 1) -> "Renamed":
    return wrapped.postponed(level)


# TODO: Add __repr__'s
# TODO: Validate obj types


__all__ = (
    "IPacket",
    "PacketWrapper",
    "PacketValidator",
    "PacketAdapter",
    "Renamed",
    "postponed",
)
