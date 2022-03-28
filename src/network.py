import asyncio
import abc
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
        return self.writer.wait_closed()

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
    async def recv(self, until: bytes) -> bytes:
        ...

    async def recv(self, arg=None, **kwargs):
        if arg is None:
            return await self.reader.read()

        if isinstance(arg, int) and kwargs.get("exactly", True):
            return await self.reader.readexactly(arg)

        if isinstance(arg, int):
            return await self.reader.read(arg)

        if isinstance(arg, bytes):
            return await self.reader.readuntil(arg)

        assert False, "Unknown overload"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @classmethod
    async def connect(cls, *args, **kwargs):
        return cls(await asyncio.open_connection(*args, **kwargs))


class BaseServer(abc.ABC):
    @property
    @abc.abstractmethod
    def handler(self):
        pass


if __name__ == "__main__":
    async def main():
        async with await Stream.connect("example.com", 80) as stream:
            await stream.send(b"GET / HTTP/1.1\r\n"
                              b"Host: example.com\r\n"
                              b"\r\n")

            # resp = await stream.recv(b"\r\n\r\n")
            resp = await stream.recv(4096, exactly=False)

            print(resp.decode())

    asyncio.run(main())
