import typing
import abc
import asyncio
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

        self._check_field_names()

    def _check_field_names(self) -> None:
        # TODO: Finish
        warnings.warn("The field name \"{}\" conflicts with an attribute of {} and will not be visible")

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
            value = self._get_value_for(field, obj)
            result.append(ctx.make_child(field.name, value=value))

        return tuple(result)

    def _children_with_contexts(self, ctx: Context,
                                obj: typing.Dict[str, typing.Any] | None = None) \
            -> typing.Iterable[typing.Tuple[IPacket, Context]]:
        return zip(self._fields, self._children_contexts_list(ctx, obj))

    async def _encode(self, stream: IStream, obj: typing.Dict[str, typing.Any], ctx: Context) -> None:
        # TODO: Perhaps elaborate?
        PacketObjTypeError.validate(obj, dict)

        encoded = bytearray()

        for field, child_ctx in self._children_with_contexts(ctx, obj):
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


__all__ = (
    "Struct",
    "StructAdapter",
    "_StructDict",
)
