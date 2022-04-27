import typing
import abc
import asyncio
import itertools
import warnings

from .ipacket import T
from ..stream import *
from ..errors import *
from .context import *
from .ipacket import *


_StructDict: typing.TypeAlias = typing.Dict[str, typing.Any]


class Struct(IPacket[_StructDict]):
    @typing.overload
    def __init__(self, name: str,
                 bases: typing.Tuple[typing.Type | "Struct"],
                 fields: _StructDict):
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
            fields: _StructDict

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

        self._check_field_names()

    def _check_field_names(self) -> None:
        checked_containers = (Context, Path)

        bad_attrs = ((cls, dir(cls())) for cls in checked_containers)

        for field, (cls, attr) in itertools.product(self._fields, bad_attrs):
            name = field.name

            if attr == name:
                warnings.warn(f"The field name \"{name}\" conflicts with an attribute of {cls} and will "
                              f"not be visible via its attribute lookup")

    @staticmethod
    def _get_value_for(field: IPacket, obj: _StructDict | None) -> typing.Any | None:
        if not obj:  # Both for None and {}
            return None

        name = field.name
        if name is None:
            return None

        return obj.get(name, None)

    def _children_contexts_list(self, ctx: Context,
                                obj: _StructDict | None = None) -> typing.Tuple[Context]:
        result: typing.List[Context] = []

        for field in self._fields:
            value = self._get_value_for(field, obj)
            result.append(ctx.make_child(field.name, value=value))

        return tuple(result)

    def _children_with_contexts(self, ctx: Context,
                                obj: _StructDict | None = None) \
            -> typing.Iterable[typing.Tuple[IPacket, Context]]:
        return zip(self._fields, self._children_contexts_list(ctx, obj))

    async def _build_with_priorities(self, ctx: Context, obj: _StructDict) -> bytes:
        encoded: typing.List[bytes] = [b''] * len(self._fields)
        ctx.set_md("enc_partial", encoded)

        for (i, (field, child_ctx)) in sorted(enumerate(
                self._children_with_contexts(ctx, obj)
        ), key=lambda x: x[1][0].postpone_level):
            substream = BytesStream()
            value = self._get_value_for(field, obj)
            await field.encode(substream, value, child_ctx)
            encoded[i] = substream.get_data()

        return b''.join(encoded)

    async def _encode_optimized(self, stream: IStream, obj: _StructDict, ctx: Context) -> None:
        encoded: typing.List[bytes] = [b''] * len(self._fields)
        ctx.set_md("enc_partial", encoded)

        for field, child_ctx in self._children_with_contexts(ctx, obj):
            value = self._get_value_for(field, obj)

            await field.encode(stream, value, child_ctx)

            encoded.append(child_ctx.encoded)

        ctx.register_enc(b''.join(encoded))

    async def _encode(self, stream: IStream, obj: _StructDict, ctx: Context) -> None:
        # TODO: Perhaps elaborate?
        PacketObjTypeError.validate(obj, dict)

        on_finish = Event[[]]()
        ctx.set_md("on_finish", on_finish)

        if all(field.postpone_level == 0 for field in self._fields):
            await self._encode_optimized(stream, obj, ctx)
        else:
            data: bytes = await self._build_with_priorities(ctx, obj)
            await stream.send(data)
            ctx.register_enc(data)

        on_finish()
        ctx.del_md("on_finish")
        ctx.del_md("enc_partial")

    async def _decode(self, stream: IStream, ctx: Context) -> _StructDict:
        result: _StructDict = {}

        on_finish = Event[[]]()
        ctx.set_md("on_finish", on_finish)

        encoded: typing.List[bytes] = [b''] * len(self._fields)
        ctx.set_md("enc_partial", encoded)

        for field, child_ctx in self._children_with_contexts(ctx):
            value = await field.decode(stream, child_ctx)

            encoded.append(child_ctx.encoded)

            if field.name is not None:
                result[field.name] = value

        ctx.register_enc(b''.join(encoded))

        on_finish()
        ctx.del_md("on_finish")
        ctx.del_md("enc_partial")

        return result

    def _sizeof(self, ctx: Context) -> int:
        result: int = 0

        for field, child_ctx in self._children_with_contexts(ctx):
            result += field.sizeof(child_ctx)

        return result


class StructAdapter(PacketAdapter[T, _StructDict], typing.Generic[T], metaclass=abc.ABCMeta):
    def __init__(self, wrapped: Struct, master_field: str = "data"):
        # TODO: ?
        assert isinstance(wrapped, Struct)
        super().__init__(wrapped)
        self._master_field = master_field

    def _modify_enc(self, obj: T, ctx: Context) -> _StructDict:
        return {self._master_field: obj}

    def _modify_dec(self, obj: _StructDict, ctx: Context) -> T:
        return obj[self._master_field]

    def __repr__(self):
        return f"{type(self).__name__}"


def enc_partial(path: Path = this) -> typing.Callable[[Context], typing.List[bytes] | None]:
    return lambda ctx: path.as_ctx(ctx).get_md("enc_partial")


def joined_enc_partial(path: Path = this) -> typing.Callable[[Context], bytes | None]:
    return lambda ctx: b''.join(enc_partial(path)(ctx))


__all__ = (
    "Struct",
    "StructAdapter",
    "_StructDict",
    "enc_partial",
    "joined_enc_partial",
)
