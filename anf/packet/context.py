import abc
import typing


T = typing.TypeVar("T")


class Context:
    KEEP_ENCODED: typing.ClassVar[bool] = True

    def __init__(self,
                 parent: typing.Optional["Context"] = None,
                 value: typing.Any | None = None):
        self.parent: Context | None = parent
        self._value_set: bool = False
        self._value: typing.Any = value
        self.encoded: bytes | None = None
        self.members: typing.Dict[str, Context] = {}

    @property
    def value(self) -> typing.Any:
        if not self._value_set:
            raise AttributeError("Value not yet set")

        return self._value

    @value.setter
    def value(self, val: typing.Any):
        self._value_set = True
        self._value = val

    def get_member(self, name: str) -> "Context":
        if name == "":
            return self

        if name == "_":
            if self.parent is None:
                raise KeyError("Context has no parent")
            return self.parent

        return self.members[name]

    def __getattr__(self, item: str) -> typing.Any:
        return self.get_member(item)

    def make_child(self, name: str) -> "Context":
        ctx = Context(self)
        self.members[name] = ctx
        return ctx

    def register_val(self, value: T) -> T:
        self.value = value
        return value

    def register_enc(self, data: bytes) -> bytes:
        self.encoded = data
        return data


class Path:
    def __init__(self, initial: str | typing.Iterable[str] | "Path" = (), encoded: bool = False):
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

    def encoded(self, value: bool = True):
        self._encoded = value

    @staticmethod
    def _split_path(path: str) -> list[str]:
        return path.split("/")

    def __truediv__(self, other: typing.Any) -> "Path":
        copy = Path(self.path, self._encoded)

        copy /= other

        return copy

    def __itruediv__(self, other: typing.Any) -> "Path":
        if isinstance(other, str):
            other = self._split_path(other)

        assert all(isinstance(name, str) for name in other), "A path must only consist of strings"

        self.path += other

        return self

    def __call__(self, ctx: Context) -> typing.Any:
        for name in self.path:
            ctx = ctx.get_member(name)

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
