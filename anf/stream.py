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
    async def recv(self, size: int = -1, *, exactly: bool = True) -> bytes:
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

    @staticmethod
    def _check_eof(data: bytes, size: int = None) -> bytes:
        assert isinstance(data, bytes)

        if not data and (size is None or size > 0):
            raise StreamReadError("EOF was hit")

        return data


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

    async def recv(self, size: int | None = None, *, exactly: bool = True) -> bytes:
        try:
            if size is None:
                read = self.reader.read()
            elif exactly:
                read = self.reader.readexactly(size)
            else:
                read = self.reader.read(size)

            return self._check_eof(await read, size)
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


T = typing.TypeVar("T", bound=typing.BinaryIO)
U = typing.TypeVar("U")


class SyncStream(IStream, typing.Generic[T]):
    def __init__(self, wrapped_stream: T):
        self._wrapped_stream: T = wrapped_stream

        # TODO: Finish

    @property
    def wrapped_stream(self) -> T:
        return self._wrapped_stream

    def close(self):
        self._wrapped_stream.close()

    async def wait_closed(self):
        pass

    @staticmethod
    async def _repeat_while_blocking(action: typing.Callable[[], U]) -> U:
        result: U | None = None
        while result is None:
            try:
                result = action()
            except BlockingIOError:
                pass
            await asyncio.sleep(0)
        assert result is not None

        return result

    async def _send(self, data: bytes) -> None:
        data = bytearray(data)

        while data:
            written = await self._repeat_while_blocking(lambda: self.wrapped_stream.write(data))
            assert written > 0
            data[:written] = b''

        self.wrapped_stream.flush()

    async def send(self, data: bytes) -> None:
        try:
            await self._send(data)
        except (OSError,) as e:
            raise StreamWriteError from e

    async def _recv(self, size: int | None = None, exactly: bool = True) -> bytes:
        if size is None:
            size = -1
            exactly = False
        if not exactly:
            return self._check_eof(
                await self._repeat_while_blocking(
                    lambda: self.wrapped_stream.read(size)
                ), size
            )

        data = bytearray()
        while len(data) < size:
            data += self._check_eof(
                await self._repeat_while_blocking(
                    lambda: self.wrapped_stream.read(size - len(data))
                ), size
            )
        return bytes(data)

    async def recv(self, size: int | None = None, *, exactly: bool = True) -> bytes:
        try:
            return await self._recv(size, exactly=exactly)
        except (OSError,) as e:
            raise StreamReadError from e

    async def recv_until(self, until: bytes) -> bytes:
        data = bytearray()
        while not data.endswith(until):
            data += await self.recv(1, exactly=False)
        return bytes(data)

    async def recv_line(self) -> bytes:
        return await self.recv_until(b'\n')

    def at_eof(self) -> bool:
        if self.wrapped_stream.seekable():
            cur_pos = self.wrapped_stream.tell()
            end_pos = self.wrapped_stream.seek(0, io.SEEK_END)
            self.wrapped_stream.seek(cur_pos)

            return cur_pos == end_pos

        assert False, "Cannot identify eof"

    def reset(self) -> None:
        assert self.wrapped_stream.seekable()

        self.wrapped_stream.seek(0)

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
    def __init__(self, initial: bytes = b''):
        super().__init__(io.BytesIO(initial))

    def get_data(self):
        return self.wrapped_stream.getvalue()


__all__ = ("IStream", "Stream", "SyncStream", "BytesStream")
