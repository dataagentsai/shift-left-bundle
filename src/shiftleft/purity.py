"""Purity classifier (SL-PURE-01..07, core/purity.yaml). Pure analysis of Python syntax trees, no imports of the code.

Every function gets one verdict:
  impure   a call in an impure category (bindings: `purity`), a `global`/`nonlocal`, a module-level session used
           inside it, or a call to a repository function that is impure (the chain is reported)
  pure     every call is known-pure or to a repository function already found pure
  unknown  anything else: a call the checker can't see into. Unknown is never counted as pure.
"""
import ast
from dataclasses import dataclass, field
from pathlib import Path

BUILTINS_PURE = {"len", "str", "int", "float", "bool", "list", "dict", "set", "tuple", "sorted", "sum", "max", "min",
                 "round", "abs", "range", "enumerate", "zip", "isinstance", "any", "all", "map", "filter", "reversed",
                 "frozenset", "repr", "hash", "divmod", "pow", "getattr", "hasattr", "iter", "next", "type", "super"}
STR_METHODS = {"strip", "lstrip", "rstrip", "title", "upper", "lower", "capitalize", "split", "rsplit", "replace", "format",
               "join", "startswith", "endswith", "zfill", "strftime", "isoformat", "get", "keys", "values", "items", "copy"}
MUTATORS = {"append", "extend", "insert", "remove", "pop", "clear", "update", "add", "setdefault", "discard", "sort"}
CAN_PASS_IN = {"table_read", "table_write", "clock", "randomness", "global_session"}
HINTS = {"table_read": "take the DataFrame as a parameter; move the read to the caller",
         "table_write": "return the DataFrame; let the caller write it",
         "clock": "pass the time in as a parameter",
         "randomness": "pass the seed or generated value in as a parameter",
         "global_session": "pass the session in, or don't need it"}


@dataclass
class Fn:
    module: str
    name: str
    line: int
    params: set
    calls: list = field(default_factory=list)          # (dotted text, line)
    reasons: list = field(default_factory=list)        # (category, text, line)
    unknown: list = field(default_factory=list)        # (text, line)
    repo_calls: list = field(default_factory=list)     # (callee qualified name, line)
    transforms: int = 0                                # pure engine calls: the function holds logic
    marked_pure: bool = False
    verdict: str = ""
    chain: list = field(default_factory=list)

    @property
    def qname(self):
        return f"{self.module}:{self.name}"

    @property
    def categories(self):
        return {r[0] for r in self.reasons}


def dotted(node):
    """`spark.read.format("csv").load(p)` -> 'spark.read.format.load'; returns '' when the base is not a name."""
    parts = []
    while True:
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Name):
            parts.append(node.id)
            return ".".join(reversed(parts))
        elif isinstance(node, ast.Subscript):
            node = node.value
        else:
            parts.append("<expr>")
            return ".".join(reversed(parts))


def matches(text, pattern):
    """Pattern kinds: '.meth' = a method called anywhere in the chain; 'a.b' = the chain starts with it or contains it;
    'name' = the chain starts with that name (a function or a module)."""
    pattern = pattern.split(" ")[0]
    if pattern.startswith("."):
        return pattern[1:] in text.split(".")[1:]
    if "." in pattern:
        return text == pattern or text.startswith(pattern + ".") or f".{pattern}" in f".{text}"
    return text == pattern or text.startswith(pattern + ".")


class Collector(ast.NodeVisitor):
    def __init__(self, module, text):
        self.module, self.fns, self.stack = module, [], []
        self.module_globals = set()
        self.session_lines = []
        for node in ast.parse(text).body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        self.module_globals.add(t.id)
                        if "getOrCreate" in dotted(node.value) or "SparkSession" in dotted(node.value):
                            self.session_lines.append((t.id, node.lineno))

    def visit_FunctionDef(self, node):
        args = node.args
        params = {a.arg for a in args.args + args.kwonlyargs + args.posonlyargs}
        params |= {a.arg for a in (args.vararg, args.kwarg) if a}
        marked = any("pure" == dotted(d).split(".")[-1] for d in node.decorator_list)
        fn = Fn(self.module, node.name if not self.stack else f"{self.stack[-1].name}.{node.name}", node.lineno, params, marked_pure=marked)
        self.fns.append(fn)
        self.stack.append(fn)
        for child in node.body:
            self.visit(child)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        if self.stack:
            self.stack[-1].calls.append((dotted(node), node.lineno))
        self.generic_visit(node)

    def visit_Global(self, node):
        if self.stack:
            self.stack[-1].reasons.append(("global_state", "global " + ", ".join(node.names), node.lineno))

    visit_Nonlocal = visit_Global

    def visit_Name(self, node):
        if self.stack and isinstance(node.ctx, ast.Load) and node.id in {n for n, _ in self.session_lines} \
                and node.id not in self.stack[-1].params:
            self.stack[-1].reasons.append(("global_session", node.id, node.lineno))


def classify_call(text, purity):
    """-> ('impure', category) | ('pure', 'lazy_transform' or None) | ('unknown', None) for one call's dotted text.
    A chained call is judged by its own final method; the calls inside the chain are visited separately."""
    known = purity.get("known_pure", {})
    if "." in text and any(p.startswith(".") and p[1:] == text.split(".")[-1] for p in known.get("lazy_transform", [])):
        return "pure", "lazy_transform"
    for cat, pats in purity.items():
        if cat in ("known_pure", "test_guard_patch", "global_session", "global_state"):   # these two are found from the tree
            continue
        if any(matches(text, p) for p in pats):
            return "impure", cat
    head = text.split(".")[0]
    if text in BUILTINS_PURE or head in ("F", "functions", "Window", "math", "re", "decimal", "itertools", "functools",
                                         "operator", "string", "textwrap", "json") or head in known.get("standard_pure", []):
        return "pure", None
    return "unknown", None


def analyse(project: Path, purity: dict, paths):
    fns = []
    for p in paths:
        rel = str(p.relative_to(project))
        try:
            text = p.read_text(errors="ignore")
            col = Collector(rel, text)
            col.visit(ast.parse(text))
        except SyntaxError:
            continue
        fns += col.fns
    by_name = {}
    for f in fns:
        by_name.setdefault(f.name.split(".")[-1], []).append(f)
    for f in fns:
        for text, line in f.calls:
            # only plain-name calls resolve to repository functions; same module first
            cands = [g for g in by_name.get(text, []) if g is not f] if "." not in text else []
            local = sorted(cands, key=lambda g: g.module != f.module)
            kind, cat = classify_call(text, purity)
            parts = text.split(".")
            if kind == "unknown" and len(parts) == 2 and parts[1] in MUTATORS:
                kind, cat = ("impure", "global_state") if parts[0] in f.params else ("pure", None)
            elif kind == "unknown" and len(parts) >= 2 and parts[-1] in STR_METHODS:
                kind = "pure"
            if cat == "lazy_transform":
                f.transforms += 1
            if kind == "impure":
                f.reasons.append((cat, text, line))
            elif local and kind != "pure":
                f.repo_calls.append((local[0].qname, line))
            elif kind == "unknown":
                f.unknown.append((text, line))
    index = {f.qname: f for f in fns}
    for f in fns:                                           # own evidence first
        f.verdict = "impure" if f.reasons else ""
    changed = True
    while changed:                                          # spread through repository calls until stable
        changed = False
        for f in fns:
            if f.verdict == "impure":
                continue
            callees = [index[q] for q, _ in f.repo_calls if q in index]
            bad = [c for c in callees if c.verdict == "impure"]
            if bad:
                f.verdict, f.chain = "impure", [bad[0].qname] + bad[0].chain
                f.reasons.append(("calls_impure", bad[0].qname, next(ln for q, ln in f.repo_calls if q == bad[0].qname)))
                changed = True
            elif not f.unknown and all(c.verdict == "pure" for c in callees) and f.verdict != "pure":
                f.verdict = "pure"
                changed = True
    for f in fns:
        if not f.verdict:
            f.verdict = "unknown"
    return fns


def could_be_pure(f):
    """Impure only through things the caller can pass in, and it holds logic (engine transforms) worth testing."""
    cats = f.categories - {"calls_impure", "output", "engine_action"}
    return f.verdict == "impure" and cats and cats <= CAN_PASS_IN and f.transforms > 0


def hint(f):
    return "; ".join(HINTS[c] for c in sorted(f.categories & CAN_PASS_IN))


def summary(fns):
    out = {}
    for f in fns:
        m = out.setdefault(f.module, {"pure": 0, "impure": 0, "unknown": 0})
        m[f.verdict] += 1
    return out
