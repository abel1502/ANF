import abc
import typing


T = typing.TypeVar("T")


class Context:
    KEEP_ENCODED: typing.ClassVar[bool] = True

    def __init__(self,
                 parent: typing.Optional["Context"] = None,
                 value: typing.Any | None = None):
        self.parent: Context | None = parent
        self._value: typing.Any | None = value
        self.encoded: bytes | None = None
        self.members: typing.Dict[str, Context] = {}
        self.metadata: typing.Dict[str, typing.Any] = {}

    @property
    def value_or_none(self) -> typing.Any | None:
        return self._value

    @value_or_none.setter
    def value_or_none(self, val: typing.Any | None):
        self._value = val

    @property
    def value(self) -> typing.Any:
        if self._value is None:
            raise ValueError("Value not yet set")

        return self._value

    @value.setter
    def value(self, val: typing.Any):
        self.value_or_none = val

    def get_member(self, name: str) -> "Context":
        assert isinstance(name, str)

        if name == "":
            return self

        if name == "_":
            if self.parent is None:
                raise KeyError("Context has no parent")
            return self.parent

        return self.members[name]

    def get_member_or_none(self, name: str | None) -> typing.Optional["Context"]:
        if name is None:
            return None

        try:
            return self.get_member(name)
        except KeyError:
            return None

    def __getattr__(self, item: str) -> typing.Any:
        return self.get_member(item)

    def get_md(self, name: str, default=None) -> typing.Any:
        return self.metadata.get(name, default)

    def set_md(self, name: str, value: T) -> T:
        self.metadata[name] = value
        return value

    def del_md(self, name: str) -> None:
        del self.metadata[name]

    def make_child(self, name: str | None, value: typing.Any | None = None) -> "Context":
        """
        Either return the child context, or make one if it isn't yet present
        """

        ctx: Context | None = self.get_member_or_none(name)
        if ctx is None:
            ctx = Context(self, value=value)
            if name is not None:
                self.members[name] = ctx
        else:
            assert value is None  # TODO: Remove this later?
        return ctx

    def register_val(self, value: T) -> T:
        self.value = value
        return value

    def register_enc(self, data: bytes) -> bytes:
        self.encoded = data
        return data

    def __repr__(self) -> str:
        return f"Context(val={self.value_or_none}, enc={self.encoded}, {self.members}, md={self.metadata})"


# TODO: Perhaps rework to be more convenient
class Path:
    def __init__(self, initial: str | typing.Iterable[str] | "Path" = (), *,
                 or_none: bool = False):
        if isinstance(initial, Path):
            initial = initial.path
            # noinspection PyProtectedMember
            or_none = initial._or_none

        if isinstance(initial, str):
            initial = self._split_path(initial)
        else:
            initial = list(initial)

        self.path: typing.List[str] = initial
        self._or_none: bool = or_none

    def __copy__(self) -> "Path":
        return Path(self.path, or_none=self._or_none)

    # @property
    # def value(self):
    #     """
    #     Does nothing, but one might find it declarative
    #     """
    #
    #     return self

    @property
    def or_none(self):
        copy = self.__copy__()
        copy._or_none = True
        return copy

    def as_ctx(self, ctx: Context) -> Context | None:
        for name in self.path:
            get_member: typing.Callable[[str], Context | None] = \
                ctx.get_member_or_none if self._or_none else ctx.get_member
            ctx = get_member(name)

            if ctx is None and self._or_none:
                return None

        return ctx

    @staticmethod
    def _split_path(path: str) -> list[str]:
        return path.split("/")

    def __truediv__(self, other: typing.Any) -> "Path":
        copy = self.__copy__()

        copy /= other

        return copy

    def __itruediv__(self, other: typing.Any) -> "Path":
        if isinstance(other, str):
            other = self._split_path(other)

        assert all(isinstance(name, str) for name in other), "A path must only consist of strings"

        self.path += other

        return self

    def __getattr__(self, name: str) -> "Path":
        return self / name

    def __call__(self, ctx: Context) -> typing.Any:
        ctx = self.as_ctx(ctx)

        if ctx is None:
            assert self._or_none
            return None

        return ctx.value_or_none if self._or_none else ctx.value

    def __repr__(self) -> str:
        return "/".join(self.path)


def _wrap_path_func(func: typing.Callable[[typing.Any], T]) \
        -> typing.Callable[[Path], typing.Callable[[Context], T]]:
    return lambda path: lambda ctx: func(path(ctx))


this = Path("_")
this.__repr__ = lambda self: "this" + repr(super()).split("_", 1)[1]
len_ = _wrap_path_func(len)


def encoded(path: Path = this) -> typing.Callable[[Context], bytes | None]:
    return lambda ctx: path.as_ctx(ctx).encoded


CtxParam: typing.TypeAlias = T | typing.Callable[[Context], T]


def eval_ctx_param(param: CtxParam[T], ctx: Context) -> T:
    if hasattr(param, "__call__"):
        param = param(ctx)

    return param


# TODO: Perhaps use events for more advanced use cases
P = typing.ParamSpec("P")
_PCallback: typing.TypeAlias = typing.Callable[P, typing.Any]


class Event(typing.Generic[P]):
    def __init__(self):
        self._subscribed: typing.List[_PCallback] = []

    def add(self, cb: _PCallback) -> None:
        self._subscribed.append(cb)

    def rem(self, cb: _PCallback) -> None:
        self._subscribed.remove(cb)

    def clear(self):
        self._subscribed.clear()

    def fire(self, *args: P.args, **kwargs: P.kwargs) -> None:
        for cb in self._subscribed:
            cb(*args, **kwargs)

    def __iadd__(self, other: _PCallback):
        if not hasattr(other, "__call__"):
            return NotImplemented
        self.add(other)
        return self

    def __isub__(self, other: _PCallback):
        if not hasattr(other, "__call__"):
            return NotImplemented
        self.rem(other)
        return self

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> None:
        self.fire(*args, **kwargs)


__all__ = (
    "Context",
    "Path",
    "encoded",
    "this",
    "_wrap_path_func",  # TODO: ?
    "len_",
    "CtxParam",
    "eval_ctx_param",
    "Event",
)
