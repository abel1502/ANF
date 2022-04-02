import asyncio
import typing


class Stream:
    def __init__(self, rw):
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
        self.writer.write(data)
        await self.writer.drain()

    @typing.overload
    async def recv(self) -> bytes:
        ...

    @typing.overload
    async def recv(self, size: int, exactly: bool = True) -> bytes:
        ...

    @typing.overload
    async def recv(self, until: bytes | str) -> bytes:
        ...

    async def recv(self, arg=None, **kwargs):
        if arg is None:
            return await self.reader.read()

        if isinstance(arg, int) and kwargs.get("exactly", True):
            return await self.reader.readexactly(arg)

        if isinstance(arg, int):
            return await self.reader.read(arg)

        if isinstance(arg, str):
            arg = arg.encode()

        if isinstance(arg, bytes):
            return await self.reader.readuntil(arg)

        assert False, "Unknown overload"

    async def recv_line(self) -> bytes:
        data = await self.reader.readline()

        if not data.endswith(b'\n'):
            raise asyncio.IncompleteReadError(data, None)

        return data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
        await self.wait_closed()


__all__ = ("Stream",)
