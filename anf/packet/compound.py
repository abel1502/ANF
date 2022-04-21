import typing
import abc
import asyncio

from .ipacket import T
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *
from .misc import *


class Struct(IPacket[typing.Dict[str, typing.Any]]):
    @typing.overload
    def __init__(self, name: str,
                 bases: typing.Tuple[typing.Type | "Struct"],
                 fields: typing.Dict[str, typing.Any]):
        """
        The metaclass-compatible constructor
        """
        ...

    @typing.overload
    def __init__(self, *args: IPacket):
        ...

    @typing.overload
    def __init__(self, **kwargs: IPacket):
        ...

    def __init__(self, *args, **kwargs):
        assert not args or not kwargs, "Unknown overload"

        if kwargs:
            args = []
            for name, packet in kwargs.items():
                assert isinstance(packet, IPacket)
                args.append(packet.renamed(name))
            kwargs = {}

        assert not kwargs

        if len(args) == 3 and isinstance(args[1], tuple):
            name: str
            bases: typing.Tuple[typing.Type | "Struct"]
            fields: typing.Dict[str, typing.Any]

            name, bases, fields = args

            assert isinstance(name, str)
            assert isinstance(bases, tuple)
            assert isinstance(fields, dict)

            if any(map(lambda b: isinstance(b, IPacket), bases)):
                raise NotImplementedError("Struct inheritance not yet implemented")
            # TODO: Warn about bases being ignored?

            assert not kwargs

            self._name = name

            kwargs = {}
            for name, field in fields.items():
                if not isinstance(field, IPacket):
                    continue
                kwargs[name] = field

            self.__init__(**kwargs)
            return

        self._fields: typing.Tuple[IPacket, ...] = tuple(args)

    @staticmethod
    def _get_value_for(field: IPacket, obj: typing.Dict[str, typing.Any] | None) -> typing.Any | None:
        if not obj:  # Both for None and {}
            return None

        name = field.name
        if name is None:
            return None

        return obj.get(name, None)

    def _children_contexts_list(self, ctx: Context,
                                obj: typing.Dict[str, typing.Any] | None = None) -> typing.Tuple[Context]:
        result: typing.List[Context] = []

        for field in self._fields:
            result.append(ctx.make_child(field.name, value=self._get_value_for(field, obj)))

        return tuple(result)

    def _children_with_contexts(self, ctx: Context,
                                obj: typing.Dict[str, typing.Any] | None = None) \
            -> typing.Iterable[typing.Tuple[IPacket, Context]]:
        return zip(self._fields, self._children_contexts_list(ctx, obj))

    async def _encode(self, stream: IStream, obj: typing.Dict[str, typing.Any], ctx: Context) -> None:
        # TODO: Perhaps elaborate?
        PacketObjTypeError.validate(obj, dict)

        encoded = bytearray()

        for field, child_ctx in self._children_with_contexts(ctx):
            value = self._get_value_for(field, obj)

            await field.encode(stream, value, child_ctx)

            encoded += child_ctx.encoded

        ctx.register_enc(bytes(encoded))

    async def _decode(self, stream: IStream, ctx: Context) -> typing.Dict[str, typing.Any]:
        result: typing.Dict[str, typing.Any] = {}

        encoded = bytearray()

        for field, child_ctx in self._children_with_contexts(ctx):
            value = await field.decode(stream, child_ctx)

            encoded += child_ctx.encoded

            if field.name is not None:
                result[field.name] = value

        ctx.register_enc(bytes(encoded))

        return result

    def _sizeof(self, ctx: Context) -> int:
        result: int = 0

        for field, child_ctx in self._children_with_contexts(ctx):
            result += field.sizeof(child_ctx)

        return result


ST = typing.TypeVar("ST", bound=typing.Sized)


class CountPrefixed(IPacket[ST]):
    def __init__(self, count_field: IPacket[int], data_field: typing.Callable[[int], IPacket[ST]]):
        self.count_field: IPacket[int] = count_field.renamed("count")
        self.data_field: typing.Callable[[int], IPacket[ST]] = \
            lambda length: data_field(length).renamed("data")

    async def _encode(self, stream: IStream, obj: ST, ctx: Context) -> None:
        obj_len = len(obj)
        count_field = self.count_field
        data_field = self.data_field(obj_len)

        count_ctx = ctx.make_child(count_field.name)
        data_ctx = ctx.make_child(data_field.name)

        encoded = bytearray()

        await count_field.encode(stream, obj_len, count_ctx)
        encoded += count_ctx.encoded
        await data_field.encode(stream, obj, data_ctx)
        encoded += data_ctx.encoded

        ctx.register_enc(encoded)

    async def _decode(self, stream: IStream, ctx: Context) -> ST:
        encoded = bytearray()

        count_field = self.count_field
        count_ctx = ctx.make_child(count_field.name)
        obj_len = await count_field.decode(stream, count_ctx)
        encoded += count_ctx.encoded

        data_field = self.data_field(obj_len)
        data_ctx = ctx.make_child(data_field.name)
        obj: ST = await data_field.decode(stream, data_ctx)
        encoded += data_ctx.encoded

        ctx.register_enc(encoded)

        if len(obj) != obj_len:
            raise PacketEncodeError("Unexpected data length")

        return obj

    def _sizeof(self, ctx: Context) -> int:
        count_field = self.count_field
        count_ctx: Context = ctx.get_member(count_field.name)
        data_field = self.data_field(count_ctx.value)
        data_ctx: Context = ctx.get_member(data_field.name)

        return count_field.sizeof(count_ctx) + data_field.sizeof(data_ctx)


# TODO: Encapsulate in some sort of restreamed, perhaps?
class SizePrefixed(IPacket[T]):
    def __init__(self, count_field: IPacket[int], data_field: IPacket[T]):
        self.size_field: IPacket[int] = count_field.renamed("size")
        self.data_field: IPacket[T] = data_field.renamed("data")

    async def _encode(self, stream: IStream, obj: T, ctx: Context) -> None:
        size_field = self.size_field
        data_field = self.data_field

        size_ctx = ctx.make_child(size_field.name)
        data_ctx = ctx.make_child(data_field.name)

        sub_stream = BytesStream()
        await data_field.encode(sub_stream, obj, data_ctx)

        enc = sub_stream.get_data()

        await size_field.encode(stream, len(enc), size_ctx)
        await stream.send(enc)

    async def _decode(self, stream: IStream, ctx: Context) -> T:
        size_field = self.size_field
        size_ctx = ctx.make_child(size_field.name)
        obj_size = await size_field.decode(stream, size_ctx)

        sub_stream = BytesStream(await stream.recv(obj_size))

        data_field = self.data_field
        data_ctx = ctx.make_child(data_field.name)
        obj: T = await data_field.decode(sub_stream, data_ctx)

        return obj

    def _sizeof(self, ctx: Context) -> int:
        size_field = self.size_field
        size_ctx: Context = ctx.get_member(size_field.name)

        return size_field.sizeof(size_ctx) + size_ctx.value


__all__ = (
    "Struct",
    "CountPrefixed",
    "SizePrefixed",
)
