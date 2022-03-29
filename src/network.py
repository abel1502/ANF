import asyncio
import abc
import datetime
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
        self.close()
        await self.wait_closed()

    @classmethod
    async def connect(cls, host: str, port: int, **kwargs):
        return cls(await asyncio.open_connection(host, port, **kwargs))


class BaseServerHandler(abc.ABC):
    def __init__(self, server: "BaseServer"):
        self.server = server

    @abc.abstractmethod
    async def handle(self, stream: Stream) -> None:
        pass


class BaseServer(abc.ABC):
    def __init__(self):
        self._server: (asyncio.AbstractServer | None) = None
        self.verbose = True

    def wait_closed(self) -> typing.Awaitable[None]:
        return self.server_impl.wait_closed()

    async def run(self, port: int, host: (str | None) = None, background=False, **kwargs):
        self.log("Starting...")
        self._server = await asyncio.start_server(self._callback, host, port, **kwargs)

        self.log("Awaiting connections")
        serve_forever = self.server_impl.serve_forever()

        if background:
            asyncio.create_task(serve_forever)
            return

        try:
            await serve_forever
            await self.wait_closed()
        except asyncio.CancelledError:
            pass
        self.log("Done.")

    def close(self):
        if self.server_impl.is_serving():
            self.log("Shutting down...")
        self.server_impl.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
        await self.wait_closed()

    @property
    def server_impl(self) -> asyncio.AbstractServer:
        if self._server is None:
            raise RuntimeError("Server not started")

        return self._server

    @abc.abstractmethod
    def get_handler(self) -> BaseServerHandler:
        pass

    async def _callback(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        async with Stream((reader, writer)) as stream:
            await self.get_handler().handle(stream)

    # noinspection PyMethodMayBeStatic
    def format_log_msg(self, msg: str) -> str:
        return "[SERVER] [{time:%H:%M:%S}] {msg}".format(time=datetime.datetime.today(), msg=msg)

    def log(self, msg: str, *args, **kwargs):
        if not self.verbose:
            return

        msg = msg.format(*args, **kwargs)
        msg = self.format_log_msg(msg)
        print(msg)


if __name__ == "__main__":
    async def test_example_com():
        async with await Stream.connect("example.com", 80) as stream:
            await stream.send(b"GET / HTTP/1.1\r\n"
                              b"Host: example.com\r\n"
                              b"\r\n")

            # resp = await stream.recv(b"\r\n\r\n")
            resp = await stream.recv(4096, exactly=False)

            print(resp.decode())

    class Server(BaseServer):
        class Handler(BaseServerHandler):
            async def handle(self, stream: Stream) -> None:
                while True:
                    try:
                        cmd = await stream.recv(b"\n")
                        cmd = cmd.decode().strip()
                        match cmd:
                            case "quit":
                                await stream.send(b"Bye!\n")
                                break
                            case "stop":
                                await stream.send(b"Stopping...\n")
                                self.server.close()
                                await self.server.wait_closed()
                                return
                            case _:
                                await stream.send(f"{cmd}\n".encode())
                    except asyncio.IncompleteReadError:
                        # TODO: Handler.log()?
                        self.server.log("Client disconnected...")
                        break

        def get_handler(self) -> BaseServerHandler:
            return self.Handler(self)


    async def test_server():
        async def run_server():
            async with Server() as srv:
                srv: Server

                await srv.run(18878)

        async def run_client():
            async with await Stream.connect("localhost", 18878) as stream:
                async def send_cmd(cmd: str):
                    print(f"> {cmd}")
                    await stream.send(f"{cmd}\n".encode())

                    data = await stream.recv(b"\n")
                    print("<", data.decode().rstrip("\n"))

                await send_cmd("Hello!")
                await send_cmd("stop")

        server = asyncio.create_task(run_server())
        client = asyncio.create_task(run_client())

        await client
        await server

    async def main():
        # await test_example_com()

        await test_server()

    asyncio.run(main())
