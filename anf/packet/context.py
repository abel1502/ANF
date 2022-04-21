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
            raise AttributeError("Value not yet set")

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


# TODO: Perhaps rework to be more convenient
class Path:
    def __init__(self, initial: str | typing.Iterable[str] | "Path" = (), *,
                 encoded: bool = False, or_none: bool = False):
        if isinstance(initial, Path):
            # noinspection PyProtectedMember
            encoded = initial._encoded
            initial = initial.path

        if isinstance(initial, str):
            initial = self._split_path(initial)
        else:
            initial = list(initial)

        self.path: typing.List[str] = initial
        self._encoded: bool = encoded
        self._or_none: bool = or_none

    def encoded(self, value: bool = True):
        self._encoded = value

    def or_none(self, value: bool = True):
        self._or_none = value

    @staticmethod
    def _split_path(path: str) -> list[str]:
        return path.split("/")

    def __truediv__(self, other: typing.Any) -> "Path":
        copy = Path(self.path, encoded=self._encoded, or_none=self._or_none)

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
        for name in self.path:
            get_member: typing.Callable[[str], Context | None] = \
                ctx.get_member_or_none if self._or_none else ctx.get_member
            ctx = get_member(name)

        if self._or_none:
            return ctx.encoded if self._encoded else ctx.value_or_none
        if self._encoded and ctx.encoded is None:
            raise KeyError("Field not yet encoded")
        return ctx.encoded if self._encoded else ctx.value

    def __repr__(self) -> str:
        return "/".join(self.path)


def _wrap_path_func(func: typing.Callable[[typing.Any], T]) \
        -> typing.Callable[[Path], typing.Callable[[Context], T]]:
    return lambda path: lambda ctx: func(path(ctx))


this = Path("_")
this.__repr__ = lambda self: "this" + repr(super()).split("_", 1)[1]
len_ = _wrap_path_func(len)


CtxParam: typing.TypeAlias = T | typing.Callable[[Context], T]


def eval_ctx_param(param: CtxParam[T], ctx: Context) -> T:
    if hasattr(param, "__call__"):
        param = param(ctx)

    return param


__all__ = (
    "Context",
    "Path",
    "this",
    "len_",
    "CtxParam",
    "eval_ctx_param",
)
