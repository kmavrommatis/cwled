"""
Mermaid diagram generation for CWL Workflows.

Provides :class:`CWLMermaidGenerator`, which turns a CWL Workflow into a
Mermaid ``graph TD`` flow-chart.

Nodes
-----
* workflow inputs        -> ``input_<port_id>``
* workflow steps         -> ``step_<step_id>``  (a single node per step;
    step input/output *port details are intentionally omitted*)
* workflow outputs       -> ``output_<port_id>``

Edges express the data-flow: ``input -> step -> step -> output``.

Steps whose ``run`` references another Workflow are expanded into a separate,
still-connected ``subgraph`` block showing that sub-workflow's individual
steps, so nested pipelines can be visualised in a single diagram.

The produced Mermaid text can be consumed by the ``nf-metro`` library to
render a transit-like diagram for pipeline documentation.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import data
from ports import PortSplitter
from CWLparser import Parser


class CWLMermaidGenerator:
    """
    Generate a Mermaid flow-chart from a CWL Workflow.

    The generator accepts a :class:`CWLparser.Parser`, a ``cwl_utils``
    Workflow object, or a raw CWL dictionary.  Sub-workflow steps (a step
    whose ``run`` is another Workflow) are expanded into nested
    ``subgraph`` blocks that remain connected to the parent pipeline.

    Args:
        cwl_workflow: A CWL Workflow as a ``Parser``, a ``cwl_utils`` object,
            or a dict.
        orientation: Mermaid graph direction, one of ``TD``, ``LR``, ``BT``,
            ``RL``.  Defaults to ``TD``.
        base_dir: Directory used to resolve relative ``run`` paths of steps.
            Defaults to the parent of the loaded workflow file when a
            ``Parser`` is supplied.
        label_steps: When ``True`` use a step's ``label`` (falling back to its
            ``id``) as the node label.  Defaults to ``True``.
        show_scatter: When ``True`` scatter/gather steps are drawn with a
            distinct node shape.  Defaults to ``True``.
    """

    def __init__(
        self,
        cwl_workflow: Union[Parser, Any, dict],
        orientation: str = "TD",
        base_dir: Optional[Union[str, Path]] = None,
        label_steps: bool = True,
        show_scatter: bool = True,
    ):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(data.configuration.get("logLevel", {}).get(self.__class__.__name__, "DEBUG"))

        self.orientation = orientation if orientation in {"TD", "LR", "BT", "RL"} else "TD"
        self.label_steps = label_steps
        self.show_scatter = show_scatter

        self.base_dir: Optional[Path] = Path(base_dir) if base_dir is not None else None

        self.workflow, parser = self._normalize(cwl_workflow)
        if parser is not None and getattr(parser, "path", None) is not None and self.base_dir is None:
            self.base_dir = parser.path.parent

        if not hasattr(self.workflow, "class_") or self.workflow.class_ != "Workflow":
            raise TypeError(
                "CWLMermaidGenerator requires a CWL Workflow, "
                f"got {getattr(self.workflow, 'class_', 'unknown')}"
            )

        self.wf_id = str(getattr(self.workflow, "id", "") or "workflow").split("#")[-1]
        self.wf_label = str(getattr(self.workflow, "label", "") or self.wf_id)

        # working state
        self.lines: List[str] = []
        self.nodes: Set[str] = set()
        self.edges: Set[Tuple[str, str]] = set()
        self.indent = 0
        self._visited: Set[int] = set()
        self._max_depth = 8

    # ------------------------------------------------------------------ #
    # Normalisation
    # ------------------------------------------------------------------ #
    def _normalize(self, cwl_workflow: Any) -> Tuple[Any, Optional[Parser]]:
        """Return ``(cwl_utils Workflow object, Parser-or-None)``."""
        if isinstance(cwl_workflow, Parser):
            obj = cwl_workflow.getCWL()
            if obj is None:
                raise ValueError("Parser does not contain a loaded CWL document")
            return obj, cwl_workflow

        if isinstance(cwl_workflow, dict):
            # Route through Parser so IDs/sources are normalised the same way
            # as for file-loaded workflows (_strip_ids, _strip_source, ...).
            parser = Parser(cwl_workflow, fileuri="cwled://dict-input")
            obj = parser.getCWL()
            return obj, parser

        if hasattr(cwl_workflow, "class_"):
            return cwl_workflow, None

        raise TypeError(f"Unsupported CWL workflow input of type {type(cwl_workflow)}")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _sanitize_id(value: Any) -> str:
        """Make a value safe to use as a Mermaid node identifier."""
        s = str(value).split("#")[-1]
        s = re.sub(r"[^A-Za-z0-9_]", "_", s)
        if not s:
            s = "node"
        if s[0].isdigit():
            s = "n_" + s
        return s

    def _step_id(self, step: Any) -> str:
        return self._sanitize_id(getattr(step, "id", "step"))

    def _port_id(self, value: Any) -> str:
        return self._sanitize_id(value)

    def _step_label(self, step: Any) -> str:
        if self.label_steps and getattr(step, "label", None):
            return str(step.label)
        return self._step_id(step)

    def _is_scatter(self, step: Any) -> bool:
        return self.show_scatter and bool(getattr(step, "scatter", None))

    def _is_subworkflow_step(self, step: Any) -> bool:
        run = getattr(step, "run", None)
        if run is None:
            return False
        if hasattr(run, "class_") and getattr(run, "class_") == "Workflow":
            return True
        if isinstance(run, str) and run.strip():
            return Path(run).suffix.lower() in {".cwl", ".yaml", ".yml", ".json"}
        return False

    def _load_subworkflow(self, step: Any) -> Optional[Parser]:
        """Load the sub-workflow referenced by a step's ``run`` field."""
        run = getattr(step, "run", None)
        if run is None:
            return None

        # Embedded CWL object that is a Workflow
        if hasattr(run, "class_") and getattr(run, "class_") == "Workflow":
            try:
                return Parser(run)
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.warning("Could not wrap embedded sub-workflow: %s", exc)
                return None

        # File path to a CWL document
        if isinstance(run, str) and run.strip():
            run_path = Path(run)
            if not run_path.is_absolute() and self.base_dir is not None:
                run_path = self.base_dir / run_path
            try:
                if run_path.exists():
                    sub_parser = Parser(run_path)
                    if getattr(sub_parser.cwl_tool, "class_", None) == "Workflow":
                        return sub_parser
            except Exception as exc:
                self.logger.warning("Could not load sub-workflow %s: %s", run, exc)
        return None

    def _resolve_sources(self, source: Any, workflow_id: str) -> List[Tuple[str, str]]:
        """
        Resolve a CWL ``source`` / ``outputSource`` value to a list of
        ``("input" | "step", port-or-step-id)`` producers.

        After :meth:`CWLparser.Parser._strip_source` / ``_strip_outputSource``
        a source is either ``step_id/port_id`` (a step output) or a bare
        ``port_id`` (a workflow input).
        """
        results: List[Tuple[str, str]] = []
        if source is None:
            return results
        sources = source if isinstance(source, list) else [source]
        for src in sources:
            if not src:
                continue
            try:
                ps = PortSplitter(str(src), workflow_id=workflow_id)
            except ValueError:
                self.logger.debug("Could not split source %r", src)
                continue
            if ps.step_id:
                # Nested / scattered steps such as "a/b/out" -> top step "a"
                top_step = ps.step_id.split("/")[0]
                results.append(("step", top_step))
            else:
                results.append(("input", ps.port_id))
        return results

    # ------------------------------------------------------------------ #
    # Mermaid emission
    # ------------------------------------------------------------------ #
    def _out(self, text: str) -> None:
        self.lines.append("    " * self.indent + text)

    def _add_node(self, node_id: str, label: str, scatter: bool = False) -> None:
        if node_id in self.nodes:
            return
        self.nodes.add(node_id)
        safe_label = str(label).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        if scatter and self.show_scatter:
            # Stadium shape marks scatter / gather steps
            self._out(f'{node_id}{{{safe_label}}}')
        else:
            self._out(f'{node_id}["{safe_label}"]')

    def _add_edge(self, frm: str, to: str) -> None:
        if frm == to:
            return
        key = (frm, to)
        if key in self.edges:
            return
        self.edges.add(key)
        self._out(f"{frm} --> {to}")

    def _emit_workflow(
        self,
        wf: Any,
        base_dir: Optional[Path],
        scope: str,
        in_subgraph: bool,
        depth: int = 0,
    ) -> None:
        """
        Recursively emit one workflow level.

        ``scope`` prefixes node ids so nested workflows never collide.
        Input and output nodes are only emitted at the top level; inside a
        subgraph only steps and their inter-step edges are shown, with the
        subgraph block itself acting as the connection boundary to the parent
        pipeline.
        """
        if id(wf) in self._visited or depth > self._max_depth:
            return
        self._visited.add(id(wf))

        wf_id = str(getattr(wf, "id", "") or "workflow").split("#")[-1]

        if in_subgraph:
            sg_id = f"{scope}sg"
            self._out(f"subgraph {sg_id}")
            self._out("direction TB")
            self.indent += 1

        # --- inputs (top level only) --------------------------------- #
        if not in_subgraph:
            for inp in getattr(wf, "inputs", None) or []:
                pid = self._port_id(getattr(inp, "id", ""))
                nid = f"{scope}i_{pid}"
                self._add_node(nid, pid)

        # --- steps --------------------------------------------------- #
        step_node: Dict[str, str] = {}
        for step in getattr(wf, "steps", None) or []:
            sid = self._step_id(step)
            sub_parser = self._load_subworkflow(step)
            if sub_parser is not None:
                # Nested workflow -> its own connected subgraph block
                sg_id = f"{scope}sg_{sid}"
                step_node[sid] = sg_id
                sub_base = sub_parser.path.parent if getattr(sub_parser, "path", None) else base_dir
                sub_scope = f"{scope}{sid}_"
                self._emit_workflow(sub_parser.cwl_tool, sub_base, sub_scope, True, depth + 1)
            else:
                nid = f"{scope}s_{sid}"
                step_node[sid] = nid
                self._add_node(nid, self._step_label(step), scatter=self._is_scatter(step))

        # --- edges: inputs / upstream steps -> steps ----------------- #
        for step in getattr(wf, "steps", None) or []:
            sid = self._step_id(step)
            to_node = step_node.get(sid, f"{scope}s_{sid}")
            for step_input in getattr(step, "in_", None) or []:
                for ptype, pid in self._resolve_sources(
                    getattr(step_input, "source", None), wf_id
                ):
                    # Sub-workflow inputs enter via the subgraph boundary,
                    # not via an explicit node inside the block.
                    if in_subgraph and ptype == "input":
                        continue
                    if ptype == "input":
                        frm = f"{scope}i_{pid}"
                    else:
                        top = pid.split("/")[0]
                        frm = step_node.get(top, f"{scope}s_{top}")
                    self._add_edge(frm, to_node)

        # --- outputs: steps -> outputs (top level only) -------------- #
        if not in_subgraph:
            for outp in getattr(wf, "outputs", None) or []:
                pid = self._port_id(getattr(outp, "id", ""))
                nid = f"{scope}o_{pid}"
                self._add_node(nid, pid)
                for ptype, pid in self._resolve_sources(
                    getattr(outp, "outputSource", None), wf_id
                ):
                    if ptype == "step":
                        top = pid.split("/")[0]
                        frm = step_node.get(top, f"{scope}s_{top}")
                        self._add_edge(frm, nid)
                    elif ptype == "input":
                        frm = f"{scope}i_{pid}"
                        self._add_edge(frm, nid)

        if in_subgraph:
            self.indent -= 1
            self._out("end")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def generate(self) -> str:
        """Return the Mermaid ``graph TD`` text for the workflow."""
        self.lines = []
        self.nodes = set()
        self.edges = set()
        self.indent = 0
        self._visited = set()

        self._out(f"graph {self.orientation}")
        self._out(f"%% CWL Workflow: {self.wf_id}")
        if self.wf_label and self.wf_label != self.wf_id:
            self._out(f"%% {self.wf_label}")

        self._emit_workflow(self.workflow, self.base_dir, "", False)

        return "\n".join(self.lines)

    def to_block(self, lang: str = "mermaid") -> str:
        """Return the diagram wrapped in fenced Markdown code blocks."""
        return f"```{lang}\n{self.generate()}\n```"

    def save_mmd(self, path: Union[str, Path]) -> None:
        """Write the Mermaid diagram to a ``.mmd`` file."""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(self.generate(), encoding="utf-8")
        self.logger.info("Wrote Mermaid diagram to %s", out_path)

    def documentation_block(self, title: str = "Pipeline diagram") -> str:
        """Markdown containing the Mermaid diagram, ready to embed in ``doc``."""
        return f"## {title}\n\n{self.to_block()}\n"

    def embed_in_documentation(self, title: str = "Pipeline diagram") -> str:
        """Insert the Mermaid diagram into the workflow ``doc`` field.

        Existing documentation is preserved and the diagram section is
        appended.  Returns the resulting ``doc`` string.
        """
        block = self.documentation_block(title=title)
        existing = getattr(self.workflow, "doc", None) or ""
        if existing.strip():
            self.workflow.doc = existing.rstrip() + "\n\n" + block
        else:
            self.workflow.doc = block
        self.logger.info("Embedded Mermaid diagram into workflow documentation")
        return self.workflow.doc
