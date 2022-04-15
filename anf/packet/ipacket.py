import asyncio
import typing
import abc
import io

from ..stream import *
from ..errors import *
from .context import *


T = typing.TypeVar("T")


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

        return await self._decode(stream, ctx)

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
            stream = io.BytesIO()
            obj = args[0]
        elif len(args) == 2:
            stream, obj = args
        else:
            assert False, "Unknown overload"

        stream = SyncStream.create_from(stream)

        asyncio.get_event_loop().run_until_complete(
            self.encode(stream, obj)
        )

        if len(args) == 1:
            assert isinstance(stream, BytesStream)
            return stream.get_data()

    def decode_sync(self, stream: typing.BinaryIO | bytes) -> T:
        """
        Encodes the packet synchronously

        :param stream: The synchronous stream or a byte sequence to decode from
        :return: The decoded object
        """

        if isinstance(stream, (bytes, bytearray, memoryview)):
            stream = io.BytesIO(stream)

        return asyncio.get_event_loop().run_until_complete(
            self.decode(SyncStream.create_from(stream))
        )

    def sizeof(self, ctx: Context | None = None) -> int:
        """
        Returns the size of the struct, if it is constant-size.

        :param ctx: The current context, if present
        :raises errors.NotConstSizeable: if the packet's size depends on its contents
        """

        if ctx is None:
            ctx = Context()

        return self._sizeof(ctx)

    ####################
    # Abstract methods #
    ####################

    @abc.abstractmethod
    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        pass

    @abc.abstractmethod
    async def _decode(self, stream: IStream, ctx: Context) -> T:
        pass

    # @abc.abstractmethod
    def _sizeof(self, ctx: Context) -> int:
        try:
            return len(ctx.get_self(encoded=True))
        except KeyError:
            raise NotSizeableError("Packet wasn't yet encoded, and size cannot be determined")


class PacketWrapper(IPacket):
    def __init__(self, wrapped: IPacket):
        self.wrapped = wrapped

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        return await self.wrapped._encode(stream, obj, ctx)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        return await self.wrapped._decode(stream, ctx)

    def _sizeof(self, ctx: Context) -> int:
        return self.wrapped._sizeof(ctx)


class PacketValidator(PacketWrapper):
    def __init__(self, wrapped: IPacket):
        super().__init__(wrapped)

    def validate(self, ctx: Context) -> None:
        if not self._validate(ctx):
            raise PacketInvalidError("Validation failed")

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        self.validate(ctx)
        return await self.wrapped._encode(stream, obj, ctx)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        obj: T = await self.wrapped._decode(stream, ctx)
        self.validate(ctx)
        return obj

    @abc.abstractmethod
    def _validate(self, ctx: Context) -> bool:
        pass


U = typing.TypeVar("U")


class PacketAdapter(PacketWrapper):
    def __init__(self, wrapped: IPacket):
        super().__init__(wrapped)

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        return await self.wrapped._encode(stream, self._preprocess_enc(obj, ctx), ctx)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        return self._preprocess_dec(await self.wrapped._decode(stream, ctx), ctx)

    @abc.abstractmethod
    def _preprocess_enc(self, obj: T, ctx: Context) -> U:
        pass

    @abc.abstractmethod
    def _preprocess_dec(self, obj: U, ctx: Context) -> T:
        pass


# TODO: Add __repr__'s


__all__ = (
    "IPacket", "Context"
)
