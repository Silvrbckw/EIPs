from typing import Any, BinaryIO, Optional as PyOptional, TypeVar, Type, cast
from remerkleable.basic import uint256
from remerkleable.complex import MonoSubtreeView
from remerkleable.core import BasicView, View, ViewHook
from remerkleable.tree import Gindex, Node, PairNode, get_depth, subtree_fill_to_contents, zero_node

T = TypeVar('T', bound="Optional")

class Optional(MonoSubtreeView):
    __slots__ = ()

    def __new__(cls, value: PyOptional[Type[T]] = None, backing: PyOptional[Node] = None, hook: PyOptional[ViewHook] = None, **kwargs):
        if backing is not None:
            if value is not None:
                raise Exception("cannot have both a backing and a value to init Optional")
            return super().__new__(cls, backing=backing, hook=hook, **kwargs)

        elem_cls = cls.element_cls()
        assert cls.limit() == 1
        input_views = []
        if value is not None:
            if isinstance(value, View):
                input_views.append(value)
            else:
                input_views.append(elem_cls.coerce_view(value))
        input_nodes = cls.views_into_chunks(input_views)
        contents = subtree_fill_to_contents(input_nodes, cls.contents_depth())
        backing = PairNode(contents, uint256(len(input_views)).get_backing())
        return super().__new__(cls, backing=backing, hook=hook, **kwargs)

    def __class_getitem__(cls, element_type) -> Type["Optional"]:
        if element_type.min_byte_length() == 0:
            raise Exception(f"Invalid option type: ${element_type}")

        limit = 1
        contents_depth = get_depth(limit)
        packed = isinstance(element_type, BasicView)

        class SpecialOptionView(Optional):
            @classmethod
            def is_packed(cls) -> bool:
                return packed

            @classmethod
            def contents_depth(cls) -> int:
                return contents_depth

            @classmethod
            def element_cls(cls) -> Type[View]:
                return element_type

            @classmethod
            def limit(cls) -> int:
                return limit

        SpecialOptionView.__name__ = SpecialOptionView.type_repr()
        return SpecialOptionView

    def length(self) -> int:
        ll_node = super().get_backing().get_right()
        ll = cast(uint256, uint256.view_from_backing(node=ll_node, hook=None))
        return int(ll)

    def value_byte_length(self) -> int:
        if self.length() == 0:
            return 0
        elem_cls = self.__class__.element_cls()
        return (
            elem_cls.type_byte_length()
            if elem_cls.is_fixed_byte_length()
            else cast(View, el).value_byte_length()
        )

    def get(self) -> PyOptional[View]:
        return None if self.length() == 0 else super().get(0)

    def set(self, v: PyOptional[View]) -> None:
        if v is None:
            if self.length() == 0:
                return
            i = 0
            target = to_gindex(i, self.__class__.tree_depth())
            set_last = self.get_backing().setter(target)
            next_backing = set_last(zero_node(0))
            can_summarize = (target & 1) == 0
            if can_summarize:
                while (target & 1) == 0 and target != 0b10:
                    target >>= 1
                summary_fn = next_backing.summarize_into(target)
                next_backing = summary_fn()
            new_length = uint256(i).get_backing()
        else:
            if self.length() == 1:
                super().set(0, v)
                return
            i = 0
            elem_type: Type[View] = self.__class__.element_cls()
            if not isinstance(v, elem_type):
                v = elem_type.coerce_view(v)
            target = to_gindex(i, self.__class__.tree_depth())
            set_last = self.get_backing().setter(target, expand=True)
            next_backing = set_last(v.get_backing())
            new_length = uint256(i + 1).get_backing()

        set_length = next_backing.rebind_right
        next_backing = set_length(new_length)
        self.set_backing(next_backing)

    def __repr__(self):
        value = self.get()
        if value is None:
            return f"{self.type_repr()}(None)"
        else:
            return f"{self.type_repr()}(Some({repr(value)}))"

    @classmethod
    def type_repr(cls) -> str:
        return f"Optional[{cls.element_cls().__name__}]"

    @classmethod
    def is_packed(cls) -> bool:
        raise NotImplementedError

    @classmethod
    def contents_depth(cls) -> int:
        raise NotImplementedError

    @classmethod
    def tree_depth(cls) -> int:
        return cls.contents_depth() + 1  # 1 extra for length mix-in

    @classmethod
    def limit(cls) -> int:
        raise NotImplementedError

    @classmethod
    def deserialize(cls: Type[T], stream: BinaryIO, scope: int) -> Type[T]:
        if scope == 0:
            return cls()
        else:
            return cls(cls.element_cls().deserialize(stream, scope))

    def serialize(self, stream: BinaryIO) -> int:
        v = self.get()
        return 0 if v is None else v.serialize(stream)

    @classmethod
    def navigate_type(cls, key: Any) -> Type[View]:
        if key >= cls.limit():
            raise KeyError
        return super().navigate_type(key)

    @classmethod
    def key_to_static_gindex(cls, key: Any) -> Gindex:
        if key == '__is_some__':
            return RIGHT_GINDEX
        if key >= cls.limit():
            raise KeyError
        return super().key_to_static_gindex(key)

    @classmethod
    def default_node(cls) -> Node:
        return PairNode(zero_node(cls.contents_depth()), zero_node(0))  # mix-in 0 as list length

    @classmethod
    def is_fixed_byte_length(cls) -> bool:
        return False

    @classmethod
    def min_byte_length(cls) -> int:
        return 0

    @classmethod
    def max_byte_length(cls) -> int:
        elem_cls = cls.element_cls()
        return elem_cls.max_byte_length()
