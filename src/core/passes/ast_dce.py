import re
from luaparser import ast
from luaparser.astnodes import *

# Stormworks entry points always kept
_ENTRY_RE = re.compile(r'^(on[A-Z].*|httpReply)$')


class AST_DCEPass:
    """
    Dead Code Elimination (DCE) Pass
    Builds a call graph and removes unreachable functions, including unreferenced
    export-table entries in `return { ... }` modules.
    """

    def __init__(self):
        self.defined_funcs: dict = {}
        self.references: dict = {'__init__': set()}
        self.current_scope = ['__init__']
        self.export_keys: set = set()
        self.export_refs: set = set()
        self.parse_error: str | None = None

    def _traverse(self, node, in_export_table=False, export_key=None):
        if not isinstance(node, Node):
            return

        is_func = False
        name = None

        if isinstance(node, Return):
            for v in node.values:
                if isinstance(v, Table):
                    for field in v.fields:
                        key_name = None
                        if isinstance(field.key, String):
                            key_name = field.key.s
                        elif isinstance(field.key, Name):
                            key_name = field.key.id
                        if key_name and isinstance(field.value, (Function, AnonymousFunction)):
                            self.defined_funcs[key_name] = field.value
                            if key_name not in self.references:
                                self.references[key_name] = set()
                            self.export_keys.add(key_name)
                            self.current_scope.append(key_name)
                            self._traverse(field.value, in_export_table=True, export_key=key_name)
                            self.current_scope.pop()
                            continue
                        self._traverse(field.value, in_export_table=True, export_key=key_name)

        if isinstance(node, (Function, LocalFunction)):
            if isinstance(node.name, Name):
                name = node.name.id
            elif isinstance(node.name, Index):
                if isinstance(node.name.idx, String):
                    name = node.name.idx.s
                elif isinstance(node.name.idx, Name):
                    name = node.name.idx.id
            if name:
                is_func = True

        elif isinstance(node, (Assign, LocalAssign)):
            for t, v in zip(node.targets, node.values):
                if isinstance(t, Name) and isinstance(v, (Function, AnonymousFunction)):
                    name = t.id
                    is_func = True
                    break
                if isinstance(t, Index) and isinstance(v, (Function, AnonymousFunction)):
                    if isinstance(t.idx, String):
                        name = t.idx.s
                    elif isinstance(t.idx, Name):
                        name = t.idx.id
                    is_func = True
                    break

        if is_func and name and name not in self.defined_funcs:
            self.defined_funcs[name] = node
            if name not in self.references:
                self.references[name] = set()
            self.current_scope.append(name)

        if not in_export_table or export_key is None:
            if isinstance(node, Name):
                self.references[self.current_scope[-1]].add(node.id)
            elif isinstance(node, Index) and isinstance(node.idx, String):
                self.references[self.current_scope[-1]].add(node.idx.s)
            elif isinstance(node, Index) and isinstance(node.idx, Name):
                self.references[self.current_scope[-1]].add(node.idx.id)
        else:
            if isinstance(node, Index) and isinstance(node.idx, String):
                self.export_refs.add(node.idx.s)
            elif isinstance(node, Name):
                self.export_refs.add(node.id)

        for key, val in vars(node).items():
            if key.startswith('_'):
                continue
            if isinstance(val, list):
                for item in val:
                    self._traverse(item, in_export_table, export_key)
            else:
                self._traverse(val, in_export_table, export_key)

        if is_func and name and self.current_scope[-1] == name:
            self.current_scope.pop()

    def process(self, code: str) -> tuple[str, int, str | None]:
        try:
            tree = ast.parse(code)
        except Exception as e:
            self.parse_error = str(e)
            return code, 0, self.parse_error

        self.defined_funcs.clear()
        self.references = {'__init__': set()}
        self.current_scope = ['__init__']
        self.export_keys.clear()
        self.export_refs.clear()
        self.parse_error = None

        self._traverse(tree)

        reachable = set()
        roots = ['__init__']
        for f in self.defined_funcs.keys():
            if _ENTRY_RE.match(f):
                roots.append(f)

        def dfs(node_name):
            if node_name in reachable:
                return
            reachable.add(node_name)
            for ref in self.references.get(node_name, []):
                if ref in self.defined_funcs:
                    dfs(ref)

        for root in roots:
            dfs(root)

        dead = set(self.defined_funcs.keys()) - reachable

        # Export table tree-shake: drop export keys never referenced externally
        for ek in self.export_keys:
            if ek not in self.export_refs and ek not in reachable:
                dead.add(ek)

        if not dead:
            return code, 0, None

        dead_nodes = [self.defined_funcs[d] for d in dead if d in self.defined_funcs]
        dead_nodes.sort(key=lambda n: getattr(n, 'start_char', 0), reverse=True)

        final_code = code
        removed = 0
        for node in dead_nodes:
            if not hasattr(node, 'start_char') or not hasattr(node, 'stop_char'):
                continue
            final_code = final_code[:node.start_char] + final_code[node.stop_char + 1:]
            removed += 1

        return final_code, removed, None


def ast_eliminate_dead_code(code: str) -> tuple[str, int, str | None]:
    pass_obj = AST_DCEPass()
    return pass_obj.process(code)
