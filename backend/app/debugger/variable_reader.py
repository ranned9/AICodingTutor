from __future__ import annotations
import time
from typing import Any

from .gdb_session import GdbSession
from .models import ExpansionBudget, VariableNode
from .mi_transport import GdbExitedError, CommandTimeoutError


class VariableReader:
    def __init__(self, session: GdbSession, budget: ExpansionBudget | None = None):
        self._session = session
        self._budget = budget or ExpansionBudget()
        self._varobj_names: list[str] = []

    def read_frame(self, frame_level: int = 0) -> list[VariableNode]:
        start = time.monotonic()
        nodes: list[VariableNode] = []
        try:
            self._session.select_frame(frame_level)
            variables = self._session.stack_list_variables()
        except (GdbExitedError, CommandTimeoutError):
            return nodes

        for var in variables:
            if len(nodes) >= self._budget.max_vars_per_stop:
                break
            if time.monotonic() - start > self._budget.soft_time_limit:
                break
            name = var.get("name", "")
            value = var.get("value", "")
            node = self._build_node_via_varobj(name, depth=0, start=start,
                                                seen=set())
            if node is None:
                node = VariableNode(name=name, value=value, kind="scalar")
            nodes.append(node)
        return nodes

    def read_expression(self, expression: str, display_name: str = "") -> VariableNode | None:
        node = self._build_node_via_varobj(
            expression, depth=0, start=time.monotonic(), seen=set()
        )
        if node is not None and display_name:
            node.name = display_name
        return node

    def read_globals(self, names: list[str] | None = None) -> list[VariableNode]:
        if not names:
            return []
        nodes: list[VariableNode] = []
        for name in names:
            try:
                # Qualify the expression so a same-named local in the selected
                # frame cannot silently masquerade as a global.
                expression = name if name.startswith("::") else f"::{name}"
                value = self._session.data_evaluate_expression(expression)
                if value:
                    node = self._build_node_via_varobj(
                        expression, depth=0, start=time.monotonic(), seen=set()
                    )
                    if node is None:
                        node = VariableNode(name=name, value=value, kind="scalar")
                    nodes.append(node)
            except (GdbExitedError, CommandTimeoutError):
                nodes.append(VariableNode(
                    name=name, available=False, unavailable_reason="unreadable"
                ))
        return nodes

    def _build_node_via_varobj(self, name: str, depth: int,
                               start: float, seen: set) -> VariableNode | None:
        if time.monotonic() - start > self._budget.soft_time_limit:
            return VariableNode(name=name, truncated=True)
        try:
            create_result = self._session.var_create(name)
        except (GdbExitedError, CommandTimeoutError):
            return None

        varobj_name = create_result.get("name", "")
        if varobj_name:
            self._varobj_names.append(varobj_name)

        var_type = create_result.get("type", "")
        value = create_result.get("value", "")
        numchild = int(create_result.get("numchild", "0"))
        kind = self._classify_type(var_type, value)

        node = VariableNode(name=name, type=var_type, kind=kind, value=value)

        if kind == "pointer" and value:
            addr = value
            if addr in seen:
                node.cycle = True
                return node
            seen = seen | {addr}

        if depth >= self._budget.max_depth:
            node.truncated = True
            return node

        # A pointer variable belongs to its stack/global scope. Its pointee is
        # rendered as a separate heap allocation by GdbDebugEngine instead.
        if kind != "pointer" and numchild > 0 and varobj_name:
            node.children = self._read_children(
                varobj_name, numchild, depth, start, seen
            )
        return node

    def _read_children(self, varobj_name: str, numchild: int,
                       depth: int, start: float,
                       seen: set) -> list[VariableNode]:
        children: list[VariableNode] = []
        try:
            raw_children = self._session.var_list_children(varobj_name)
        except (GdbExitedError, CommandTimeoutError):
            return children

        count = min(numchild, self._budget.max_children_per_aggregate)
        for i, child in enumerate(raw_children):
            if i >= count:
                break
            if time.monotonic() - start > self._budget.soft_time_limit:
                break
            child_name = child.get("exp", "")
            child_value = child.get("value", "")
            child_type = child.get("type", "")
            child_numchild = int(child.get("numchild", "0"))
            child_kind = self._classify_type(child_type, child_value)

            if child_kind == "array":
                display_name = f"[{child_name}]"
            else:
                display_name = child_name

            child_node = VariableNode(
                name=display_name, type=child_type,
                kind=child_kind, value=child_value,
            )

            if child_kind == "pointer" and child_value:
                addr = child_value
                if addr in seen:
                    child_node.cycle = True
                    children.append(child_node)
                    continue
                child_seen = seen | {addr}
            else:
                child_seen = seen

            if depth + 1 >= self._budget.max_depth:
                child_node.truncated = True
            elif child_numchild > 0:
                child_varobj = child.get("name", "")
                if child_varobj:
                    child_node.children = self._read_children(
                        child_varobj, child_numchild,
                        depth + 1, start, child_seen,
                    )
            children.append(child_node)
        return children

    @staticmethod
    def _classify_type(var_type: str, value: str) -> str:
        if not var_type:
            if value.startswith("{"):
                return "struct"
            return "scalar"
        if "[" in var_type:
            return "array"
        if "struct" in var_type:
            return "struct"
        if "union" in var_type:
            return "union"
        if "*" in var_type:
            return "pointer"
        if "enum" in var_type:
            return "enum"
        return "scalar"

    def cleanup_varobjs(self) -> None:
        for name in self._varobj_names:
            try:
                self._session.var_delete(name)
            except Exception:
                pass
        self._varobj_names.clear()
