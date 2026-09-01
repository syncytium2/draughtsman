"""Stage 1 — trace. Facts only.

Every number that ever reaches the final figure originates in this module
(SPEC.md §4). Nothing downstream may invent one.

WHY ``torch.jit.trace`` AND NOT ``fx`` OR ``export``. Measured on bugarach's
``tube``, whose ``forward`` computes an integer pool width from a parameter:

    torch.fx.symbolic_trace   TypeError: int() argument must be ... not 'Proxy'
    torch.export.export       GuardOnDataDependentSymNode
    torch.jit.trace           works, 200 nodes, shapes on every tensor value

Any design assuming ``torch.export`` excludes the first model this tool was
built for. Do not discover this again (SPEC.md §3).
"""

from __future__ import annotations

import importlib
import json
import re
import warnings
from typing import Any

from draughtsman import FORMAT

# --------------------------------------------------------------------------------
# THE CLASSIFICATION RULE, STATED HERE RATHER THAN BURIED.
#
# `tube` traces to 200 nodes, of which 153 are constants and list plumbing. §5's
# coverage check has teeth only if a human can read the thing it checks, so the
# structural nodes are set aside BY THIS RULE -- in code, in a diff, with the
# counts reported -- and coverage runs over what is left.
#
# This is the one place draughtsman drops a node without the agent saying so, and
# it is deliberately conservative: it drops only nodes that carry no computation a
# reader could see. Every op that touches a tensor's values stays. pytorch-graph's
# five omissions (the pool, the mean, the four kernels, the bypass, the concat) are
# all substantive under this rule and would all still fail the check.
STRUCTURAL_KINDS = (
    "prim::Constant",       # a literal
    "prim::ListConstruct",  # packing literals into an argument list
    "prim::TupleConstruct",
    "prim::ListUnpack",
    "prim::TupleUnpack",
    "prim::GetAttr",        # reaching a parameter or submodule off `self`
    "prim::NumToTensor",    # a Python int crossing into tensor-land
    "aten::Int",            # ... and back out
    "aten::ScalarImplicit",
    "aten::size",           # asking a shape, not changing one
    "aten::detach",         # no arithmetic
    "aten::contiguous",     # no arithmetic
)

STRUCTURAL_RULE = (
    "A node is structural if its kind is in structural_kinds: literals, list and "
    "tuple plumbing, attribute lookup, int/tensor crossings, shape queries, and "
    "no-op tensor moves. Everything that changes a tensor's values is substantive "
    "and must be covered by the spec (SPEC.md §5)."
)


# --------------------------------------------------------------------------------
# WHAT A TRACE CANNOT SEE, IN THE TRACER'S OWN WORDS.
#
# A traced constant may be an architectural quantity or it may be an
# initialisation, and `graph.json` cannot tell them apart because by the time
# torch records the value the difference is gone. bugarach's `tube` is the case
# that found this: its max-pool is `2 * kmin + 1` with
#
#     kmin = int(torch.exp(self.log_center.detach()).min().clamp(1, self.k))
#
# and `log_center` is a TRAINED parameter. At initialisation the centres are
# 1/2/4/8 samples, so kmin is 1 and the pool is 3 wide; the trained widths are
# ~4-7, which is a pool of 9-15. draughtsman drew "max-pool, width 3" and that
# is true of an untrained model only.
#
# THE DATA FLOW IS SEVERED, AND NOT BY US. `int()` on a tensor leaves tensor-land
# for Python, and `2 * kmin + 1` is then Python arithmetic torch never sees, so
# the width arrives at `max_pool1d` as a bare `prim::Constant` indistinguishable
# from a literal. No amount of provenance walking in this module recovers it --
# checked against torch 2.13 -- so draughtsman must not pretend to a precision
# the tracer denies.
#
# What IS available is that torch says so. It emits a TracerWarning naming the
# file and line where the crossing happened, and draughtsman was discarding it.
# Recording it is the whole mechanism: `check` then refuses to let a spec quote
# a traced constant as a fact until the spec says which kind it is. That is a
# decision in a diff, which is the same shape as an explicit elision, and it
# needs no hand-maintained list of "design quantities" -- a list that would go
# stale exactly when the model moved.
#
# NOTE WHAT DOES NOT CATCH THIS. Re-running the trace and comparing is no help:
# `build_tube` initialises log_center deterministically, so the baked 3 is
# perfectly reproducible. A determinism check and an architecture check are
# different claims, and only the tracer's warning separates them.
_HAZARD_PATTERNS = (
    ("python_value_baked", "Converting a tensor to a Python"),
    ("python_value_baked", "Iterating over a tensor"),
    ("shape_baked", "the trace might not generalize"),
)


def _hazards(caught) -> list[dict]:
    """TracerWarnings, deduplicated, as facts with a source location."""
    out: dict[tuple, dict] = {}
    for w in caught:
        if "TracerWarning" not in type(w.message).__name__:
            continue
        text = str(w.message).strip()
        kind = next((k for k, pat in _HAZARD_PATTERNS if pat in text), "tracer")
        path = w.filename
        # Same test `_source` uses. A bake inside torch is torch's own plumbing
        # -- `rnn.py` asking `if batch_sizes is None` -- and reflects how the
        # module was CONSTRUCTED. A bake in the model's own file is the author
        # computing something in `forward`, which is where a fitted quantity
        # turns into a literal. Only the second is evidence about this figure.
        internal = "site-packages" in path or "/torch/" in path
        file = path.rsplit("/", 1)[-1]
        key = (kind, file, w.lineno)
        out.setdefault(key, {
            "kind": kind, "file": file, "line": w.lineno,
            "internal": internal, "message": text.splitlines()[0],
        })
    return [out[k] for k in sorted(out)]


def _load_target(target: str) -> Any:
    """``pkg.module:factory`` -> the model. The factory is called with no args."""
    if ":" not in target:
        raise ValueError(
            f"target {target!r} must be 'package.module:callable' "
            "(e.g. bugarach.learn.nets.tube:build_tube)"
        )
    modname, _, attr = target.partition(":")
    mod = importlib.import_module(modname)
    obj = getattr(mod, attr)
    return obj() if callable(obj) else obj


_SRC_RE = re.compile(r"^(?P<file>.+?)\((?P<line>\d+)\)(?::\s*(?P<fn>\S+))?")


def _source(node) -> dict | None:
    """``/long/path/tube.py(142): forward`` -> a small record.

    Every substantive node in `tube` has one of these, and only the 13 that are
    registered ``nn.Module`` children have a scope. So this is not a nicety: it is
    the only attribution the functional ops -- which are the architecture -- have.
    """
    raw = node.sourceRange()
    if not raw:
        return None
    first = raw.split("\n")[0].strip()
    m = _SRC_RE.match(first)
    if not m:
        return None
    path = m.group("file")
    internal = "site-packages" in path or "/torch/" in path
    return {
        "file": path.rsplit("/", 1)[-1],
        "line": int(m.group("line")),
        "function": m.group("fn"),
        "internal": internal,
    }


def _module_path(node) -> str | None:
    """``__module.head/__module.head.0`` -> ``head.0``."""
    scope = node.scopeName()
    if not scope:
        return None
    last = scope.split("/")[-1]
    last = last.removeprefix("__module.").removeprefix("__module")
    return last.lstrip(".") or None


def _sizes(value) -> list[int] | None:
    try:
        s = value.type().sizes()
    except Exception:
        return None
    return list(s) if s is not None else None


def _ivalue(value):
    """The Python value behind a constant, or ``None``. Lists are followed."""
    node = value.node()
    if node.kind() == "prim::Constant":
        try:
            v = value.toIValue()
        except Exception:
            return None
        return v if isinstance(v, (int, float, bool, str)) or v is None else None
    if node.kind() == "prim::ListConstruct":
        out = []
        for el in node.inputs():
            v = _ivalue(el)
            if v is None and el.node().kind() != "prim::Constant":
                return None
            out.append(v)
        return out
    return None


_SCHEMA_ARGS_RE = re.compile(r"\(([^)]*)\)")


def _arg_names(node) -> list[str]:
    try:
        schema = str(node.schema())
    except Exception:
        return []
    m = _SCHEMA_ARGS_RE.search(schema)
    if not m:
        return []
    names = []
    depth = 0
    cur = ""
    for ch in m.group(1):
        if ch in "[(":
            depth += 1
        elif ch in "])":
            depth -= 1
        if ch == "," and depth == 0:
            names.append(cur)
            cur = ""
        else:
            cur += ch
    names.append(cur)
    out = []
    for part in names:
        part = part.split("=")[0].strip()
        out.append(part.split(" ")[-1].lstrip("*") if part else "")
    return out


def _shapes_and_dtypes(input_shape, dtype) -> tuple[list[list[int]], list[str]]:
    """Normalise the two accepted spellings into a list of shapes and dtypes.

    ONE INPUT IS THE COMMON CASE AND MUST NOT PAY FOR THE OTHER. ``[1, 30, 600]``
    and ``[[1, 30, 600]]`` produce identical output, and a single dtype string
    applies to every input, so every call written before multi-input existed
    still means what it meant.
    """
    flat = not input_shape or isinstance(input_shape[0], int)
    shapes = [list(input_shape)] if flat else [list(s) for s in input_shape]
    dtypes = [dtype] if isinstance(dtype, str) else list(dtype)
    if len(dtypes) == 1:
        dtypes *= len(shapes)
    if len(dtypes) != len(shapes):
        raise ValueError(
            f"{len(shapes)} input shape(s) but {len(dtypes)} dtype(s); pass one "
            "dtype for all inputs or one per input")
    return shapes, dtypes


def trace(target: str, input_shape, *, dtype="float32", seed: int = 0) -> dict:
    """Trace a model and return ``graph.json`` as a dict. Facts only.

    *input_shape* is one shape (``[1, 30, 600]``) or several
    (``[[1, 80, 300], [1, 12]]``), and *dtype* is one name for all of them or one
    per input. Several is what an encoder--decoder needs: Whisper's ``forward``
    takes the mel spectrogram AND the token ids, and a tracer that can only build
    one dummy tensor cannot call it at all -- which is a structural exclusion of
    the whole encoder--decoder family, not a hard problem.
    """
    import torch  # imported here so `render`/`check` never need torch

    shapes, dtypes = _shapes_and_dtypes(input_shape, dtype)
    torch.manual_seed(seed)
    model = _load_target(target)
    model.eval()

    xs = tuple(torch.zeros(*s, dtype=getattr(torch, d))
               for s, d in zip(shapes, dtypes))
    with torch.no_grad(), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # A one-tuple and a bare tensor trace identically; passing the tuple
        # unconditionally keeps one code path.
        graph = torch.jit.trace(model, xs, check_trace=False).inlined_graph
    hazards = _hazards(caught)

    nodes = list(graph.nodes())

    # id per node, positional so it does not shift when the classification does.
    node_id = {n: f"n{i:04d}" for i, n in enumerate(nodes)}
    producer: dict[str, str] = {}
    for n in nodes:
        for o in n.outputs():
            producer[o.debugName()] = node_id[n]
    # `self` is a graph input with no shape. It is the source of every parameter
    # lookup, so leaving it addressable would hang an edge off every conv.
    real_inputs = set()
    for i, gi in enumerate(graph.inputs()):
        producer.setdefault(gi.debugName(), f"in{i}")
        if _sizes(gi) is not None:
            real_inputs.add(f"in{i}")

    kind_of = {node_id[n]: n.kind() for n in nodes}
    structural = set(STRUCTURAL_KINDS)

    def is_substantive(nid: str) -> bool:
        return nid in kind_of and kind_of[nid] not in structural

    # -- parameter attribution -----------------------------------------------
    # Walk the GetAttr chains off `self` to find which Value is which parameter,
    # then charge each parameter to the first substantive node that consumes it.
    # `head.0`'s weight and bias both land on its convolution; `log_center` lands
    # on the exp that opens the kernel construction.
    numel = {name: p.numel() for name, p in model.named_parameters()}
    pshape = {name: list(p.shape) for name, p in model.named_parameters()}
    total_params = sum(numel.values())

    attr_name: dict[str, str] = {}          # value debugName -> dotted attr path
    self_name = next(iter(graph.inputs())).debugName()
    attr_name[self_name] = ""
    for n in nodes:  # nodes are in topological order, so one pass suffices
        if n.kind() != "prim::GetAttr":
            continue
        base = attr_name.get(next(n.inputs()).debugName())
        if base is None:
            continue
        field = n.s("name")
        path = f"{base}.{field}" if base else field
        attr_name[next(n.outputs()).debugName()] = path

    param_charge: dict[str, int] = {}
    param_names: dict[str, list[str]] = {}

    def _consumers(value, pname: str, seen: set) -> set[str]:
        """Every substantive node this parameter reaches, seeing through
        structural plumbing on the way."""
        found: set[str] = set()
        for use in value.uses():
            un = use.user
            if un not in node_id:
                continue
            nid = node_id[un]
            if is_substantive(nid):
                found.add(nid)
                continue
            key = (nid, pname)
            if key in seen:
                continue
            seen.add(key)
            for o in un.outputs():
                found |= _consumers(o, pname, seen)
        return found

    # A TIED WEIGHT IS FETCHED TWICE AND MUST BE COUNTED ONCE, AT ITS FIRST USE.
    #
    # Whisper's output projection IS its token embedding. Charging every fetch put
    # 57,100,800 parameters on a 37,184,640-parameter model -- a total a figure
    # would have printed, which is the confident-and-wrong number this whole
    # design exists to prevent. Every fetch of a parameter contributes CANDIDATES
    # and the earliest in trace order is charged, which also decides WHERE it is
    # drawn: the embedding table appears at the embedding, where a reader meets
    # it, rather than at the matmul four hundred nodes later. Unioning across
    # fetches rather than trusting the first GetAttr matters because GetAttr nodes
    # are not ordered by the uses they feed. Ids are zero-padded, so `min` is
    # trace order.
    landings: dict[str, set[str]] = {}
    for n in nodes:
        if n.kind() != "prim::GetAttr":
            continue
        out = next(n.outputs())
        pname = attr_name.get(out.debugName())
        if pname in numel:
            landings.setdefault(pname, set())
            landings[pname] |= _consumers(out, pname, set())
    for pname, landing in landings.items():
        if not landing:
            continue
        nid = min(landing)
        param_charge[nid] = param_charge.get(nid, 0) + numel[pname]
        param_names.setdefault(nid, []).append(pname)

    # -- nearest substantive tensor ancestors --------------------------------
    tensor_anc: dict[str, list[str]] = {}

    def ancestors(n) -> list[str]:
        # Follow EVERY input, tensor-typed or not, and see through structural
        # producers to what fed them. `aten::cat` takes a prim::ListConstruct, not
        # tensors: stopping at a non-tensor input loses the concat's inputs, which
        # on `tube` is precisely the bypass -- the one edge the figure exists to
        # show. Getting this wrong is silent; the graph just looks linear.
        out: list[str] = []
        for i in n.inputs():
            pid = producer.get(i.debugName())
            if pid is None:
                continue
            if pid.startswith("in"):
                if pid in real_inputs and pid not in out:
                    out.append(pid)
            elif is_substantive(pid):
                if pid not in out:
                    out.append(pid)
            else:
                for a in tensor_anc.get(pid, []):
                    if a not in out:
                        out.append(a)
        return out

    records = []
    for n in nodes:
        nid = node_id[n]
        anc = ancestors(n)
        tensor_anc[nid] = anc
        if n.kind() in structural:
            continue

        outs = []
        for o in n.outputs():
            outs.append({"value": o.debugName(), "shape": _sizes(o)})
        out_shape = outs[0]["shape"] if outs else None

        args = _arg_names(n)
        consts = {}
        for i, inp in enumerate(n.inputs()):
            if _sizes(inp) is not None:
                continue
            v = _ivalue(inp)
            if v is None:
                continue
            consts[args[i] if i < len(args) and args[i] else f"arg{i}"] = v

        records.append({
            "id": nid,
            "kind": n.kind(),
            "module": _module_path(n),
            "source": _source(n),
            "inputs": [producer.get(i.debugName()) for i in n.inputs()
                       if producer.get(i.debugName())],
            "tensor_inputs": anc,
            "outputs": outs,
            "out_shape": out_shape,
            "params": param_charge.get(nid, 0),
            "param_names": sorted(param_names.get(nid, [])),
            # Kernel width lives in the weight's shape, not in the node's
            # constants, and a figure that cannot say "kernel 3, dilation 32" is
            # not saying much. Lifted here so the spec can reference it.
            "weight_shape": next(
                (pshape[n] for n in sorted(param_names.get(nid, []))
                 if n.rsplit(".", 1)[-1] == "weight"), None),
            "constants": consts,
        })

    charged = sum(r["params"] for r in records)
    return {
        "draughtsman": FORMAT,
        "model": {
            "target": target,
            # `input_shape` is the singular convenience and is present ONLY when
            # the model takes one input. On a two-input model there is no such
            # thing, and emitting the first one under a singular name would let
            # `{model.input_shape}` render a figure that quietly describes half
            # the model's input. A spec must say which, via `{model.input_shapes[0]}`.
            **({"input_shape": shapes[0], "input_dtype": dtypes[0]}
               if len(shapes) == 1 else {}),
            "input_shapes": shapes,
            "input_dtypes": dtypes,
            "params": total_params,
            "parameters": {k: numel[k] for k in sorted(numel)},
            "parameter_shapes": {k: pshape[k] for k in sorted(pshape)},
        },
        "tracer": {
            "backend": "torch.jit.trace",
            "torch": torch.__version__,
        },
        # THE TRACER'S OWN TESTIMONY THAT IT BAKED SOMETHING. See _hazards.
        "hazards": hazards,
        "classification": {
            "rule": STRUCTURAL_RULE,
            "structural_kinds": list(STRUCTURAL_KINDS),
            "nodes_total": len(nodes),
            "nodes_substantive": len(records),
            "nodes_structural": len(nodes) - len(records),
        },
        # If this is False the figure could quote a parameter total the model does
        # not have, which is the one lie this design exists to prevent.
        "params_attributed": charged,
        "params_fully_attributed": charged == total_params,
        "inputs": [
            {"id": f"in{i}", "value": v.debugName(), "shape": _sizes(v)}
            for i, v in enumerate(graph.inputs()) if _sizes(v) is not None
        ],
        "outputs": [
            {"producer": producer.get(v.debugName()), "value": v.debugName(),
             "shape": _sizes(v)}
            for v in graph.outputs()
        ],
        "nodes": records,
    }


def dumps(doc: dict) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
