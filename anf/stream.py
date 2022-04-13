import typing
import asyncio
import abc
import io

from .errors import *


class IStream(abc.ABC):
    @abc.abstractmethod
    def close(self) -> None:
        pass

    @abc.abstractmethod
    async def wait_closed(self) -> None:
        pass

    @abc.abstractmethod
    async def send(self, data: bytes) -> None:
        """
        :raises StreamWriteError:
        """
        pass

    @abc.abstractmethod
    async def recv(self, size: int = -1, exactly: bool = True) -> bytes:
        """
        :raises StreamWriteError:
        """

        pass

    @abc.abstractmethod
    async def recv_until(self, until: bytes) -> bytes:
        """
        :raises StreamWriteError:
        """
        pass

    @abc.abstractmethod
    async def recv_line(self) -> bytes:
        """
        :raises StreamWriteError:
        """
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
        await self.wait_closed()


class Stream(IStream):
    def __init__(self, rw: typing.Tuple[asyncio.StreamReader, asyncio.StreamWriter]):
        rw = tuple(rw)

        assert len(rw) == 2
        assert isinstance(rw[0], asyncio.StreamReader)
        assert isinstance(rw[1], asyncio.StreamWriter)

        self.rw = rw

    @property
    def reader(self) -> asyncio.StreamReader:
        return self.rw[0]

    @property
    def writer(self) -> asyncio.StreamWriter:
        return self.rw[1]

    def close(self):
        self.writer.close()

    async def wait_closed(self):
        await self.writer.wait_closed()

    async def send(self, data: bytes) -> None:
        try:
            self.writer.write(data)
            await self.writer.drain()
        except (ConnectionError,) as e:
            raise StreamWriteError from e

    async def recv(self, size: int | None = None, exactly: bool = True) -> bytes:
        try:
            if size is None:
                read = self.reader.read()
            elif exactly:
                read = self.reader.readexactly(size)
            else:
                read = self.reader.read(size)

            return await read
        except (ConnectionError, asyncio.IncompleteReadError) as e:
            raise StreamReadError from e

    async def recv_until(self, until: bytes) -> bytes:
        try:
            return await self.reader.readuntil(until)
        except (ConnectionError, asyncio.IncompleteReadError) as e:
            raise StreamReadError from e

    async def recv_line(self) -> bytes:
        try:
            data = await self.reader.readline()

            if not data.endswith(b'\n'):
                raise asyncio.IncompleteReadError(data, None)

            return data
        except (ConnectionError, asyncio.IncompleteReadError) as e:
            raise StreamReadError from e

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
        await self.wait_closed()


T = typing.TypeVar("T", bound=typing.BinaryIO)


class SyncStream(IStream, typing.Generic[T]):
    def __init__(self, wrapped_stream: T):
        self._wrapped_stream: T = wrapped_stream

        # TODO: Finish

    @property
    def wrapped_stream(self) -> T:
        return self._wrapped_stream

    @staticmethod
    @typing.overload
    def create_from(obj: typing.BinaryIO) -> "SyncStream":
        ...

    @staticmethod
    @typing.overload
    def create_from(obj: bytes) -> "BytesStream":
        ...

    @staticmethod
    def create_from(obj):
        if isinstance(obj, bytes):
            return BytesStream(obj)
        else:
            return SyncStream(obj)


class BytesStream(SyncStream[io.BytesIO]):
    def __init__(self, initial: bytes):
        super().__init__(io.BytesIO(initial))

    def get_data(self):
        return self.wrapped_stream.getvalue()


__all__ = ("IStream", "Stream", "SyncStream", "BytesStream")
