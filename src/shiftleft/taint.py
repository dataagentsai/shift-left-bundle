"""Where does a value put into SQL text come from? (SL-069)

A small, bounded source trace over Python syntax trees, across the files of one repository:
    - a name is followed to its last assignment in the same scope (or the loop it walks);
    - a function parameter is followed to the function's call sites (positional, keyword or default);
    - a call to a function defined in the repo is followed into that function's return values,
      with the call's own arguments bound to the parameters.
At most MAX_HOPS function hops; anything beyond is "unknown". Each source is a (label, where) pair.

Labels: constant, config (ALL_CAPS names), widget, command-line, environment, table (read from data),
parameter (a parameter with no call site found), unknown.
"""
import ast
from dataclasses import dataclass, field
from pathlib import Path

MAX_HOPS = 2
UNTRUSTED = {"widget", "command-line", "environment"}
TRUSTED = {"constant", "config"}
ACTIONS = {"collect", "first", "head", "take", "toPandas", "toLocalIterator", "fetchall", "fetchone"}
CONVERT = {"str", "int", "float", "bool", "round", "len", "repr", "format", "list", "tuple", "sorted", "set"}


def chain(node):
    out = []
    while True:
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            out.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Name):
            return [node.id, *out[::-1]]
        else:
            return out[::-1]


def _caps(name):
    return name.replace("_", "").isupper()


@dataclass
class Index:
    """Parsed Python files of one project: trees, parent links, function definitions and call sites by name."""
    project: Path
    trees: dict = field(default_factory=dict)
    parents: dict = field(default_factory=dict)
    defs: dict = field(default_factory=dict)       # name -> [(file, FunctionDef)]
    calls: dict = field(default_factory=dict)      # name -> [(file, Call)]

    @classmethod
    def build(cls, project: Path, files):
        ix = cls(project)
        for rel in files:
            try:
                tree = ast.parse((project / rel).read_text(errors="ignore"))
            except (SyntaxError, ValueError, OSError):
                continue
            ix.trees[rel] = tree
            for p in ast.walk(tree):
                for c in ast.iter_child_nodes(p):
                    ix.parents[c] = p
                if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    ix.defs.setdefault(p.name, []).append((rel, p))
                elif isinstance(p, ast.Call):
                    name = p.func.id if isinstance(p.func, ast.Name) else (
                        p.func.attr if isinstance(p.func, ast.Attribute) else None)
                    if name:
                        ix.calls.setdefault(name, []).append((rel, p))
        return ix

    def scope(self, node):
        n = self.parents.get(node)
        while n is not None and not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = self.parents.get(n)
        return n


@dataclass
class Tracer:
    ix: Index
    memo: dict = field(default_factory=dict)

    # -------------------------------------------------------------- entry points
    def interpolations(self, stmt, file):
        """Values put into string text inside one statement: f-string fields, .format arguments, + operands."""
        out = []
        for n in ast.walk(stmt):
            if isinstance(n, ast.JoinedStr):
                out += [v.value for v in n.values if isinstance(v, ast.FormattedValue)]
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "format" \
                    and isinstance(n.func.value, ast.Constant) and isinstance(n.func.value.value, str):
                out += [*n.args, *(k.value for k in n.keywords)]
            elif isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Mod)) and any(
                    isinstance(s, ast.Constant) and isinstance(s.value, str) for s in (n.left, n.right)):
                out += [s for s in (n.left, n.right) if not isinstance(s, (ast.Constant, ast.BinOp, ast.JoinedStr))]
        if not out:   # the SQL text is in a variable: spark.sql(q) -> follow q to its f-string
            for name in [n for n in ast.walk(stmt) if isinstance(n, ast.Name)]:
                a = self._assignment(name.id, name, file)
                if a is not None and isinstance(a.value, (ast.JoinedStr, ast.BinOp, ast.Call)):
                    out += self.interpolations(a, file)
        return out

    def sources(self, expr, file, hops=0, env=None):
        """Memoised: a repeated lookup gets the stored answer; a lookup still in progress (a cycle) gets nothing."""
        bound = tuple(sorted((k, id(v[0])) for k, v in env.items())) if env else None   # syntax nodes live with the index
        key = (file, id(expr), hops, bound)
        if key in self.memo:
            return self.memo[key]
        self.memo[key] = set()
        self.memo[key] = out = self._sources(expr, file, hops, env)
        return out

    def _sources(self, expr, file, hops, env):
        where = f"{file}:{getattr(expr, 'lineno', '?')}"
        if isinstance(expr, ast.Constant):
            return {("constant", where)}
        if isinstance(expr, ast.JoinedStr):
            return set().union(set(), *(self.sources(v.value, file, hops, env) for v in expr.values
                                        if isinstance(v, ast.FormattedValue))) or {("constant", where)}
        if isinstance(expr, (ast.BinOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.Tuple, ast.List, ast.Set,
                             ast.UnaryOp)):
            kids = [c for c in ast.iter_child_nodes(expr) if isinstance(c, ast.expr)]
            if isinstance(expr, ast.IfExp):
                kids = [expr.body, expr.orelse]
            return set().union(set(), *(self.sources(k, file, hops, env) for k in kids))
        if isinstance(expr, ast.Name):
            return self._name(expr, file, hops, env)
        if isinstance(expr, (ast.Attribute, ast.Subscript)):
            ch = chain(expr)
            if ch[:2] == ["sys", "argv"]:
                return {("command-line", where)}
            if ch[:2] == ["os", "environ"]:
                return {("environment", where)}
            if ch and _caps(ch[0]):
                return {("config", where)}
            base = expr.value
            return self.sources(base, file, hops, env)
        if isinstance(expr, ast.Call):
            return self._call(expr, file, hops, env, where)
        return {("unknown", where)}

    # -------------------------------------------------------------- helpers
    def _call(self, call, file, hops, env, where):
        ch = chain(call)
        last = ch[-1] if ch else ""
        joined = ".".join(ch)
        if "widgets" in ch or last == "getArgument":
            return {("widget", where)}
        if last in ("parse_args", "parse_known_args", "input") or "argv" in ch:
            return {("command-line", where)}
        if last == "getenv" or "environ" in ch:
            return {("environment", where)}
        if ACTIONS & set(ch):
            return {("table", where)}
        if ch and _caps(ch[0]):
            return {("config", where)}
        if isinstance(call.func, ast.Name) and call.func.id in self.ix.defs and hops < MAX_HOPS:
            return self._returns(call, file, hops, env)
        if isinstance(call.func, ast.Name) and call.func.id in CONVERT or isinstance(call.func, ast.Attribute):
            parts = [*call.args, *(k.value for k in call.keywords)]
            if isinstance(call.func, ast.Attribute):
                parts.append(call.func.value)
            return set().union({("constant", where)}, *(self.sources(p, file, hops, env) for p in parts)) \
                if parts else {("unknown", where)}
        return {("unknown", f"{where} ({joined or 'call'})")}

    def _returns(self, call, file, hops, env):
        out = set()
        for dfile, fn in self.ix.defs[call.func.id][:3]:
            bound = self._bind(fn, call, file, hops, env)
            rets = [r.value for r in ast.walk(fn) if isinstance(r, ast.Return) and r.value is not None]
            for r in rets:
                out |= self.sources(r, dfile, hops + 1, bound)
        return out or {("unknown", f"{file}:{call.lineno}")}

    def _bind(self, fn, call, file, hops, env):
        """Map the function's parameters to (expression, file, hops, env) at this call site, defaults included."""
        params = [a.arg for a in fn.args.args]
        defaults = dict(zip(params[len(params) - len(fn.args.defaults):], fn.args.defaults))
        if params and params[0] in ("self", "cls") and isinstance(call.func, ast.Attribute):
            params = params[1:]                                 # obj.method(a): a binds to the 2nd parameter
        defaults.update({a.arg: d for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults) if d is not None})
        bound = {}
        for i, a in enumerate(call.args):
            if i < len(params) and not isinstance(a, ast.Starred):
                bound[params[i]] = (a, file, hops, env)
        for k in call.keywords:
            if k.arg:
                bound[k.arg] = (k.value, file, hops, env)
        for p, d in defaults.items():
            bound.setdefault(p, (d, None, hops + 1, None))
        return bound

    def _name(self, name, file, hops, env):
        where = f"{file}:{name.lineno}"
        if _caps(name.id):
            return {("config", where)}
        fn = self.ix.scope(name)
        params = {a.arg for a in (fn.args.args + fn.args.kwonlyargs)} if fn else set()
        if name.id in params:
            if env is not None:
                if name.id not in env:
                    return {("unknown", where)}
                expr, efile, ehops, eenv = env[name.id]
                return self.sources(expr, efile or file, ehops, eenv)
            return self._callers(fn, name.id, file, hops)
        a = self._assignment(name.id, name, file)
        if a is None and fn is not None:                       # a module-level name used inside a function
            a = self._assignment(name.id, name, file, module=True)
        if a is None:
            return {("unknown", where)}
        value = a.iter if isinstance(a, (ast.For, ast.comprehension)) else a.value
        return self.sources(value, file, hops, env)

    def _callers(self, fn, param, file, hops):
        """A parameter of the function that holds the finding: follow it to every call site in the repo."""
        if hops >= MAX_HOPS:
            return {("parameter", f"{file}:{fn.lineno} {fn.name}({param})")}
        sites = self.ix.calls.get(fn.name, [])
        out = set()
        for cfile, call in sites[:10]:
            bound = self._bind(fn, call, cfile, hops + 1, None)
            if param in bound:
                expr, efile, ehops, eenv = bound[param]
                out |= self.sources(expr, efile or file, ehops, eenv)
        return out or {("parameter", f"{file}:{fn.lineno} {fn.name}({param})")}

    def _assignment(self, name, node, file, module=False):
        """Last assignment (or for-loop) binding `name` before `node`, in the same function or module scope.
        module=True looks at module level whatever the line (a function may run after the module finished)."""
        scope = None if module else self.ix.scope(node)
        root = scope if scope is not None else self.ix.trees.get(file)
        if root is None:
            return None
        best = None
        for n in ast.walk(root):
            if self.ix.scope(n) is not scope or (not module and getattr(n, "lineno", 10**9) >= node.lineno):
                continue
            targets = []
            if isinstance(n, ast.Assign):
                targets = n.targets
            elif isinstance(n, (ast.AnnAssign, ast.AugAssign)) and n.value is not None:
                targets = [n.target]
            elif isinstance(n, ast.For):
                targets = [n.target]
            if any(isinstance(t, ast.Name) and t.id == name for tg in targets for t in ast.walk(tg)):
                if best is None or n.lineno > best.lineno:
                    best = n
        return best


def verdict(labels):
    """block (untrusted input reaches SQL) | warn (only data read from tables) | report (only config) | None."""
    kinds = {k for k, _ in labels}
    if kinds & UNTRUSTED:
        return "block"
    if kinds and kinds <= TRUSTED | {"table"} and "table" in kinds:
        return "warn"
    if kinds and kinds <= TRUSTED:
        return "report"
    return None
