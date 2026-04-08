"""GraphQL introspection + query auto-generation.

Pure-Python — no ``graphql-core`` dependency. We hand-parse the
introspection JSON that every server emits so agents can:

1. Fetch the full schema.
2. Enumerate every Query / Mutation / Subscription field.
3. Auto-generate a valid default query for any field (args + selection
   set), used as a baseline for IDOR / auth-bypass / injection fuzzing.
4. Walk argument types to find ID-shaped inputs that are classic IDOR
   candidates.

This keeps the module entirely offline-testable: pass any SDL-less
introspection blob and we handle it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# The canonical introspection query GraphQL servers respond to.
INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: true) {
        name
        description
        args {
          name
          description
          type { ...TypeRef }
          defaultValue
        }
        type { ...TypeRef }
        isDeprecated
      }
      inputFields {
        name
        type { ...TypeRef }
      }
      enumValues(includeDeprecated: true) { name }
    }
  }
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
      }
    }
  }
}
"""


def introspection_query() -> str:
    """Return the canonical GraphQL introspection query (single-line)."""
    return INTROSPECTION_QUERY.strip()


# ── Type unwrapping ─────────────────────────────────────────────────────


def _unwrap_type(type_ref: dict[str, Any] | None) -> tuple[str, bool, bool]:
    """Unwrap NON_NULL / LIST wrappers.

    Returns ``(base_type_name, is_list, is_non_null)``.
    """
    if type_ref is None:
        return ("Unknown", False, False)
    is_non_null = False
    is_list = False
    node = type_ref
    # Outer NON_NULL wraps the rest
    if node.get("kind") == "NON_NULL":
        is_non_null = True
        node = node.get("ofType") or {}
    if node.get("kind") == "LIST":
        is_list = True
        node = node.get("ofType") or {}
        if node.get("kind") == "NON_NULL":
            node = node.get("ofType") or {}
    name = node.get("name") or "Unknown"
    return name, is_list, is_non_null


# ── Schema wrapper ──────────────────────────────────────────────────────


@dataclass
class GraphQLField:
    name: str
    args: dict[str, dict[str, Any]]
    return_type: str
    is_list: bool
    deprecated: bool = False


@dataclass
class GraphQLSchema:
    query_type: str | None
    mutation_type: str | None
    subscription_type: str | None
    types: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_introspection(cls, data: dict[str, Any]) -> GraphQLSchema:
        """Parse a raw introspection response into a queryable schema."""
        root = data
        if "data" in data:
            root = data["data"]
        schema = root.get("__schema") or root.get("schema") or {}
        q = (schema.get("queryType") or {}).get("name")
        m = (schema.get("mutationType") or {}).get("name")
        s = (schema.get("subscriptionType") or {}).get("name")
        types: dict[str, dict[str, Any]] = {}
        for t in schema.get("types") or []:
            name = t.get("name")
            if name:
                types[name] = t
        return cls(query_type=q, mutation_type=m, subscription_type=s, types=types)

    def _type(self, name: str) -> dict[str, Any]:
        return self.types.get(name) or {}

    def fields_of(self, type_name: str) -> list[GraphQLField]:
        t = self._type(type_name)
        out: list[GraphQLField] = []
        for f in t.get("fields") or []:
            ret, is_list, _ = _unwrap_type(f.get("type"))
            args: dict[str, dict[str, Any]] = {}
            for a in f.get("args") or []:
                a_type, a_list, a_nn = _unwrap_type(a.get("type"))
                args[a["name"]] = {
                    "type": a_type,
                    "is_list": a_list,
                    "non_null": a_nn,
                    "default": a.get("defaultValue"),
                }
            out.append(
                GraphQLField(
                    name=f["name"],
                    args=args,
                    return_type=ret,
                    is_list=is_list,
                    deprecated=bool(f.get("isDeprecated")),
                )
            )
        return out

    def query_fields(self) -> list[GraphQLField]:
        return self.fields_of(self.query_type) if self.query_type else []

    def mutation_fields(self) -> list[GraphQLField]:
        return self.fields_of(self.mutation_type) if self.mutation_type else []

    def idor_candidates(self) -> list[tuple[str, GraphQLField]]:
        """Find Query/Mutation fields that take an ``id`` / ``*Id`` arg.

        These are the classic GraphQL IDOR hunting grounds — the agent
        should test each one with an ID belonging to another tenant.
        """
        candidates: list[tuple[str, GraphQLField]] = []
        for kind, fields in (
            ("Query", self.query_fields()),
            ("Mutation", self.mutation_fields()),
        ):
            for fld in fields:
                for arg_name in fld.args:
                    if arg_name == "id" or arg_name.lower().endswith("id"):
                        candidates.append((kind, fld))
                        break
        return candidates

    def generate_query(self, field_name: str, *, kind: str = "query") -> str:
        """Emit a minimal-but-valid query/mutation document for a field.

        Arguments are stubbed with safe placeholders (``1`` for Int IDs,
        ``"test"`` for strings). The selection set is populated with up
        to 3 scalar sub-fields from the return type.
        """
        if kind == "query":
            fields = {f.name: f for f in self.query_fields()}
        elif kind == "mutation":
            fields = {f.name: f for f in self.mutation_fields()}
        else:
            raise ValueError("kind must be 'query' or 'mutation'")
        fld = fields.get(field_name)
        if fld is None:
            raise KeyError(f"no {kind} field named {field_name!r}")

        arg_strs: list[str] = []
        for name, meta in fld.args.items():
            placeholder = self._placeholder(meta["type"])
            arg_strs.append(f"{name}: {placeholder}")

        selection = self._default_selection(fld.return_type, depth=2)

        head = f"{kind} {{ {field_name}"
        if arg_strs:
            head += "(" + ", ".join(arg_strs) + ")"
        if selection:
            head += " " + selection
        head += " }"
        return head

    def _placeholder(self, type_name: str) -> str:
        lower = type_name.lower()
        if lower in ("int", "float"):
            return "1"
        if lower == "boolean":
            return "true"
        if lower == "id":
            return '"1"'
        if lower == "string":
            return '"test"'
        # Input object or enum — use null which may or may not be accepted
        return "null"

    def _default_selection(self, type_name: str, *, depth: int) -> str:
        if depth <= 0:
            return ""
        t = self._type(type_name)
        if not t or t.get("kind") not in ("OBJECT", "INTERFACE"):
            return ""
        picks: list[str] = []
        for f in (t.get("fields") or [])[:5]:
            ret, _is_list, _ = _unwrap_type(f.get("type"))
            ret_t = self._type(ret)
            if ret_t and ret_t.get("kind") == "SCALAR":
                picks.append(f["name"])
            if len(picks) >= 3:
                break
        if not picks:
            return ""
        return "{ " + " ".join(picks) + " }"
