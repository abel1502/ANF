import typing
import asyncio
import io
import math
from anf.packet.integral import *
from anf.packet.bytestr import *
from anf.packet.struct import *
from anf.packet.tunneling import *
from anf.packet.ipacket import *
from anf.packet.misc import *
from anf.packet.context import *
from anf.stream import *


T = typing.TypeVar("T")


async def test(packet: IPacket[T], obj: T, verbose: bool = True) -> bool:
    if verbose:
        print("packet:", packet)
        print("obj:", obj)
    stream = BytesStream()
    await packet.encode(stream, obj)
    enc = stream.get_data()
    if verbose:
        print("enc:", enc.hex())
    stream.reset()
    dec = await packet.decode(stream)
    if verbose:
        print("dec:", dec)

    return obj == dec


def _gen_my_struct(idx: int) -> Struct:
    match idx:
        case 0:
            MyStruct = Struct(
                magic=Const(b"ABEL"),
                id=VarInt,
                msg=CountPrefixed(VarInt, BytesPacket),
            )
        case 1:
            class MyStruct(metaclass=Struct):
                magic = Const(b"ABEL")
                id = VarInt
                msg = CountPrefixed(VarInt, BytesPacket)
        case 2:
            MyStruct = Struct(
                "magic" / Const(b"ABEL"),
                "id" / VarInt,
                "msg" / CountPrefixed(VarInt, BytesPacket),
                NoOpPacket,  # Only this way you can add unnamed fields
            )
        case _:
            assert False, "Wrong idx"
    return MyStruct


async def main():
    my_struct = _gen_my_struct(2)
    my_struct_val = dict(id=123, msg=b"Woah, structs too?!")

    options = (
        (VarInt, 0),
        (ZigZag, 12345678),
        (BytesPacket(4), b'abel'),
        (CountPrefixed(VarInt, BytesPacket), b'Abel is the best!'),
        (SizePrefixed(UInt8, BytesIntPacket(12, False)), 123456),
        (my_struct, my_struct_val, False),
        (PaddedPacket(VarInt, 4), 123456),
        (PaddedString(32), "Привет юникоду")
    )

    for option in options:
        if len(option) == 2:
            option = (*option, True)

        packet, obj, check = option

        result: bool = await test(packet, obj)

        if check and not result:
            print("ERROR!  ^^^")

        print()


if __name__ == "__main__":
    asyncio.run(main())


exit(0)


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
