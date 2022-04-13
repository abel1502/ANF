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

    async def encode(self, stream: IStream, obj: T) -> None:
        """
        Encodes the packet asynchronously.

        :param stream: The asynchronous stream to encode to
        :param obj: The object to encode

        :raises StreamWriteError: if writing to the stream fails
        :raises PacketEncodeError: upon errors specific to encoding the packet
            (not network-related ones)
        """

        assert isinstance(stream, IStream), self._MSG_WRONG_ASYNC.format("encode")

        return await self._encode(stream, obj)

    async def decode(self, stream: IStream) -> T:
        """
        Decodes the packet asynchronously.

        :param stream: The asynchronous stream to decode from
        :return: The decoded object

        :raises StreamReadError: if reading from the stream fails
        :raises PacketDecodeError: upon errors specific to encoding the packet
            (not network-related ones)
        """

        assert isinstance(stream, IStream), self._MSG_WRONG_ASYNC.format("decode")

        return await self._decode(stream)

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

        asyncio.get_event_loop().run_until_complete(
            self.encode(SyncStream.create_from(stream), obj)
        )

        if len(args) == 1:
            return stream.getvalue()

    def decode_sync(self, stream: typing.BinaryIO | typing.SupportsBytes) -> T:
        """
        Encodes the packet synchronously

        :param stream: The synchronous stream or a byte sequence to decode from
        :return: The decoded object
        """

        if isinstance(stream, typing.SupportsBytes):
            stream = io.BytesIO(bytes(stream))

        return asyncio.get_event_loop().run_until_complete(
            self.decode(SyncStream.create_from(stream))
        )

    def sizeof(self) -> int:
        """
        Returns the size of the struct, if it is constant-size.

        :raises errors.NotConstSizeable: if the packet's size depends on its contents
        """
        return self._sizeof()

    ####################
    # Abstract methods #
    ####################

    @abc.abstractmethod
    async def _encode(self, stream: IStream, obj: T) -> None:
        pass

    @abc.abstractmethod
    async def _decode(self, stream: IStream) -> T:
        pass

    @abc.abstractmethod
    def _sizeof(self) -> int:
        pass


__all__ = (
    "IPacket",
)
