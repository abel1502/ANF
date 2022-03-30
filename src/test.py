from network import *
from packet import *


async def test_example_com():
    async with await connect("example.com", 80) as stream:
        await stream.send(b"GET / HTTP/1.1\r\n"
                          b"Host: example.com\r\n"
                          b"\r\n")

        # resp = await stream.recv(b"\r\n\r\n")
        resp = await stream.recv(4096, exactly=False)

        print(resp.decode())


StringPacket = DynamicBytesPacket.create_simple(1, name="StringPacket")


class CmdPacket(CompoundPacket):
    members = CompoundPacket.parse_definition(
        (UInt64Packet, "cmd"),
        (StringPacket, "arg")
    )

    @property
    def cmd(self) -> int:
        return typing.cast(UInt64Packet, self.member("cmd")).value

    @cmd.setter
    def cmd(self, value: int):
        self.member("cmd").value = value

    @property
    def arg(self) -> str:
        return typing.cast(StringPacket, self.member("arg")).data.decode()

    @arg.setter
    def arg(self, value: str | bytes):
        if isinstance(value, str):
            value = value.encode()
        typing.cast(StringPacket, self.member("arg")).data = value

    @typing.overload
    def __init__(self):
        pass

    @typing.overload
    def __init__(self, cmd: int, arg: str | bytes = ""):
        pass

    def __init__(self, *args):
        match args:
            case []:
                super().__init__(UInt64Packet(), StringPacket())
                return
            case [int()]:
                cmd = args[0]
                arg = ""
            case [int(), str()]:
                cmd = args[0]
                arg = args[1].encode()
            case [int(), bytes()]:
                cmd = args[0]
                arg = args[1]
            case _:
                assert False, "Wrong argument types"

        super().__init__(UInt64Packet(cmd), StringPacket(arg))


class Server(BaseServer):
    class Handler(BaseServerHandler):
        async def handle(self, stream: Stream) -> None:
            while True:
                try:
                    # cmd = await stream.recv(b"\n")
                    # cmd = cmd.decode().strip()
                    # match cmd:
                    #     case "quit":
                    #         await stream.send(b"Bye!\n")
                    #         break
                    #     case "stop":
                    #         await stream.send(b"Stopping...\n")
                    #         self.server.close()
                    #         await self.server.wait_closed()
                    #         return
                    #     case _:
                    #         await stream.send(f"{cmd}\n".encode())

                    packet = CmdPacket()

                    await packet.decode(stream)

                    self.server.log("Got {}", packet)

                    match packet.cmd:
                        case 0:
                            await CmdPacket(0, packet.arg).encode(stream)
                        case 1:
                            await CmdPacket(0, "Bye!").encode(stream)
                            break
                        case 2:
                            await CmdPacket(0, "Stopping...").encode(stream)
                            self.server.close()
                            await self.server.wait_closed()
                            return
                except asyncio.IncompleteReadError:
                    # TODO: Handler.log()?
                    self.server.log("Client disconnected...")
                    break

    def get_handler(self) -> BaseServerHandler:
        return self.Handler(self)


async def run_server():
    async with Server() as srv:
        srv: Server

        await srv.run(18878)


async def run_client():
    async with await connect("localhost", 18878) as stream:
        # async def send_cmd(cmd: str):
        #     print(f"> {cmd}")
        #     await stream.send(f"{cmd}\n".encode())
        #
        #     data = await stream.recv(b"\n")
        #     print("<", data.decode().rstrip("\n"))
        #
        # await send_cmd("Hello!")
        # await send_cmd("stop")

        # async def send_cmd(cmd: int, arg: str):
        #     print(f"> {cmd} {arg}")
        #     await CmdPacket(cmd=cmd, arg=arg.encode()).encode(stream)
        #
        #     data = CmdPacket()
        #     await data.decode(stream)
        #     print("<", data.cmd, data.arg.rstrip(b'\0').decode())
        #
        # await send_cmd(0, "Hello")
        # await send_cmd(2, "")

        TwoCmdPackets = CompoundPacket.create(CmdPacket, CmdPacket, name="TwoCmdPackets")

        data = TwoCmdPackets(CmdPacket(0, "Hi!"), CmdPacket(2, "..."))
        print(">", data)
        await data.encode(stream)

        data.clear()
        await data.decode(stream)
        print("<", data)


async def test_server():
    server = asyncio.create_task(run_server())
    client = asyncio.create_task(run_client())

    await client
    await server


async def main():
    # await test_example_com()

    await test_server()


if __name__ == "__main__":
    asyncio.run(main())
