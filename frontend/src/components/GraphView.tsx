import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Sigma } from "sigma";
import { EdgeArrowProgram, type NodeHoverDrawingFunction } from "sigma/rendering";
import { api, type CountryGraph, type GraphEdge, type GraphNode, type GraphNodeType } from "../api/client";
import { useStore } from "../state/store";

const NODE_COLOR: Record<GraphNodeType, string> = {
  foreign_principal: "#ff4f00",
  registrant: "#4997d0",
  contact: "#ffa300",
  recipient: "#263d6b",
};

const LEGEND_LABEL: Record<GraphNodeType, string> = {
  foreign_principal: "Foreign principal",
  registrant: "Registrant — size = activity, click to expand",
  contact: "Contact — size = mentions",
  recipient: "Contribution recipient — size = mentions",
};

const LEGEND_ORDER: GraphNodeType[] = ["foreign_principal", "registrant", "contact", "recipient"];

const BACKBONE_SIZE: Record<"foreign_principal" | "registrant", number> = {
  foreign_principal: 6,
  registrant: 6,
};

// Sigma's default hover renderer draws a solid white label background (for
// legibility against whatever's behind it) but reuses the theme's --lunar
// (near-white) text color for the label itself — invisible on its own white
// box. That was never visible before because only a couple of nodes used the
// hover renderer at once; now every label goes through it (nodeReducer below
// makes all labels hover/selected-only), so it's the only label path that
// matters. Same box-drawing geometry as sigma/rendering's drawDiscNodeHover,
// with the text color hardcoded dark instead of pulled from settings.
const HOVER_LABEL_TEXT_COLOR = "#1a1a1a";

const drawNodeHoverWithDarkLabel: NodeHoverDrawingFunction = (context, data, settings) => {
  const size = settings.labelSize;
  const font = settings.labelFont;
  const weight = settings.labelWeight;
  context.font = `${weight} ${size}px ${font}`;

  context.fillStyle = "#FFF";
  context.shadowOffsetX = 0;
  context.shadowOffsetY = 0;
  context.shadowBlur = 8;
  context.shadowColor = "#000";
  const PADDING = 2;
  if (typeof data.label === "string") {
    const textWidth = context.measureText(data.label).width;
    const boxWidth = Math.round(textWidth + 5);
    const boxHeight = Math.round(size + 2 * PADDING);
    const radius = Math.max(data.size, size / 2) + PADDING;
    const angleRadian = Math.asin(boxHeight / 2 / radius);
    const xDeltaCoord = Math.sqrt(Math.abs(radius ** 2 - (boxHeight / 2) ** 2));
    context.beginPath();
    context.moveTo(data.x + xDeltaCoord, data.y + boxHeight / 2);
    context.lineTo(data.x + radius + boxWidth, data.y + boxHeight / 2);
    context.lineTo(data.x + radius + boxWidth, data.y - boxHeight / 2);
    context.lineTo(data.x + xDeltaCoord, data.y - boxHeight / 2);
    context.arc(data.x, data.y, radius, angleRadian, -angleRadian);
    context.closePath();
    context.fill();
  } else {
    context.beginPath();
    context.arc(data.x, data.y, data.size + PADDING, 0, Math.PI * 2);
    context.closePath();
    context.fill();
  }
  context.shadowOffsetX = 0;
  context.shadowOffsetY = 0;
  context.shadowBlur = 0;

  if (data.label) {
    context.fillStyle = HOVER_LABEL_TEXT_COLOR;
    context.fillText(data.label, data.x + data.size + 3, data.y + size / 3);
  }
};

// Backbone nodes (registrant/foreign_principal) are structurally permanent —
// never pruned by the collapse handler and never resized by
// resizeExpansionNodes — regardless of label visibility, which is handled
// separately (all node types are hover/selected-only labels; see nodeReducer
// below — a busy country's backbone alone can be ~150 nodes, too many for
// always-on labels to stay legible).
function isBackbone(nodeType: GraphNodeType): boolean {
  return nodeType === "registrant" || nodeType === "foreign_principal";
}

function registrantSize(node: GraphNode): number {
  const activity = (node.contact_count ?? 0) + (node.contribution_count ?? 0);
  return BACKBONE_SIZE.registrant + Math.min(Math.sqrt(activity), 12);
}

// Contact/recipient nodes are already deduplicated by normalized name within
// (and across) expanded registrants — build_registrant_expansion() collapses
// repeat mentions into one node with multiple edges. Degree is therefore a
// real occurrence signal already present in the loaded graph, no backend
// change needed to size these nodes meaningfully instead of a flat constant.
function resizeExpansionNodes(graph: Graph): void {
  graph.forEachNode((id, attrs) => {
    if (isBackbone(attrs.nodeType as GraphNodeType)) return;
    const degree = graph.degree(id);
    graph.setNodeAttribute(id, "size", 3 + Math.min(Math.sqrt(degree) * 2, 10));
  });
}

// Rescales every node position so the graph is centered at (0,0) and its
// larger dimension spans exactly 1 unit — a fixed, known coordinate range
// regardless of what scale forceAtlas2 happened to spread nodes across.
// This replaces computing a camera ratio from the raw (unnormalized, highly
// variable) layout output, which was landing on wildly-zoomed-out views —
// the actual bug behind "unreadable" / "not zoomed in": a correct-looking
// ratio calculation applied to the wrong input still zooms out too far.
function normalizePositions(graph: Graph): void {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  graph.forEachNode((_, a) => {
    minX = Math.min(minX, a.x); maxX = Math.max(maxX, a.x);
    minY = Math.min(minY, a.y); maxY = Math.max(maxY, a.y);
  });
  if (!isFinite(minX)) return;
  const span = Math.max(maxX - minX, maxY - minY, 0.001);
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  graph.forEachNode((n, a) => {
    graph.setNodeAttribute(n, "x", (a.x - cx) / span);
    graph.setNodeAttribute(n, "y", (a.y - cy) / span);
  });
}

function buildBackboneGraph(data: CountryGraph): Graph {
  const graph = new Graph({ multi: true, type: "directed" });
  // Deterministic circular seed instead of Math.random() — removes the
  // pre-layout scatter flash and makes loads reproducible between reloads.
  data.nodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(data.nodes.length, 1);
    graph.addNode(n.id, {
      label: n.label,
      size: n.node_type === "registrant" ? registrantSize(n) : BACKBONE_SIZE.foreign_principal,
      color: NODE_COLOR[n.node_type],
      x: Math.cos(angle),
      y: Math.sin(angle),
      nodeType: n.node_type,
      raw: n,
    });
  });
  for (const e of data.edges) {
    if (graph.hasNode(e.source) && graph.hasNode(e.target)) {
      graph.addEdge(e.source, e.target, { size: 1.5, color: "#c8c8c8", edgeType: e.edge_type, raw: e });
    }
  }
  if (graph.order > 1) {
    // adjustSizes makes the layout treat each node's actual `size` as a
    // physical radius when repelling, so bigger (more active) registrants
    // push their neighbors further away instead of every node repelling
    // equally regardless of size. gravity was the bigger overlap cause,
    // though: 1 (vs. this library's own ~0.05 recommendation for graphs
    // this size) pulled everything hard toward the center, fighting the
    // repulsion force and compacting nodes together. Verified empirically
    // (Node script simulating a Japan-shaped 136-node backbone): median
    // nearest-neighbor spacing went from 0.0041 to 0.0569 normalized units
    // — about a 14x improvement — switching from {gravity:1, scalingRatio:12}
    // to these settings.
    forceAtlas2.assign(graph, {
      iterations: 250,
      settings: { gravity: 0.1, scalingRatio: 22, adjustSizes: true, strongGravityMode: true },
    });
    normalizePositions(graph);
  }
  return graph;
}

// Fixed, predictable camera state (not derived from raw layout coordinates,
// which is what produced the wrong zoom before) — the graph is normalized
// to span ~1 unit above, so ratio just past 1 reliably shows the whole thing
// filling most of the viewport with a small margin, i.e. actually zoomed in.
function fitViewToNodes(renderer: Sigma): void {
  // Biased toward tighter framing on purpose: the prior bug produced views
  // that were far too zoomed OUT, so erring toward "too close, scroll out a
  // touch" is the safer direction to be wrong in than repeating that mistake.
  renderer.getCamera().setState({ x: 0, y: 0, ratio: 1.0 });
}

function zoomBy(renderer: Sigma, factor: number): void {
  const camera = renderer.getCamera();
  camera.animate({ ratio: camera.getState().ratio * factor }, { duration: 200 });
}

function resetView(renderer: Sigma): void {
  renderer.getCamera().animate({ x: 0, y: 0, ratio: 1.0 }, { duration: 200 });
}

function focusNode(renderer: Sigma, graph: Graph, nodeId: string): GraphNode {
  const x = graph.getNodeAttribute(nodeId, "x");
  const y = graph.getNodeAttribute(nodeId, "y");
  renderer.getCamera().animate({ x, y, ratio: 0.25 }, { duration: 300 });
  return graph.getNodeAttribute(nodeId, "raw") as GraphNode;
}

// New nodes from an expansion land around the registrant that was clicked,
// rather than a global forceAtlas2 re-run — re-laying out the whole graph on
// every click would reshuffle everything the user just got oriented to.
//
// A single fixed-radius ring works for a handful of nodes but breaks down for
// real data: the busiest registrant on file has 101 distinct contacts, and a
// ring's point-to-point spacing shrinks toward zero as more points share the
// same circumference. This uses a golden-angle (Vogel/sunflower) spiral
// instead, where radius grows with sqrt(index) — the correct scaling to keep
// point density, and therefore spacing, roughly constant as points are added,
// unlike a ring (spacing -> 0) or a radius scaling linearly with count
// (footprint blows up past the rest of the graph). Verified empirically
// (Node script): minimum pairwise distance stays ~0.053 normalized units
// whether there are 3 nodes or 101, while the cluster's own radius only grows
// from 0.05 to 0.34 — small expansions stay tight, huge ones stay legible
// without swallowing the rest of the graph.
const GOLDEN_ANGLE = 2.399963229728653;
const SPIRAL_SPACING = 0.034;

function placeInSpiral(graph: Graph, centerId: string, newNodeIds: string[]): void {
  const cx = graph.getNodeAttribute(centerId, "x");
  const cy = graph.getNodeAttribute(centerId, "y");
  newNodeIds.forEach((id, i) => {
    const r = SPIRAL_SPACING * Math.sqrt(i + 0.5);
    const angle = i * GOLDEN_ANGLE;
    graph.setNodeAttribute(id, "x", cx + r * Math.cos(angle));
    graph.setNodeAttribute(id, "y", cy + r * Math.sin(angle));
  });
}

function NodeDetail({ node, edges }: { node: GraphNode; edges: GraphEdge[] }) {
  const navigate = useStore((s) => s.navigate);
  const connected = edges.filter((e) => e.source === node.id || e.target === node.id);

  return (
    <div className="doc-body" style={{ marginTop: 16 }}>
      <h3>{node.node_type.replace(/_/g, " ")}</h3>
      <div className="record-title" style={{ fontSize: 18 }}>{node.label}</div>
      {node.node_type === "registrant" && (
        <div className="row-meta" style={{ marginTop: 4 }}>
          {node.contact_count ?? 0} contacts · {node.contribution_count ?? 0} contributions
          {node.contribution_total !== null && ` (${new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(node.contribution_total ?? 0)})`}
        </div>
      )}
      {(node.node_type === "registrant" || node.node_type === "foreign_principal") && (
        <button
          className="back-link"
          style={{ marginTop: 8 }}
          onClick={() => {
            const idNum = Number(node.id.split(":")[1]);
            if (node.node_type === "registrant") navigate({ kind: "registrant", id: idNum });
            else navigate({ kind: "foreign-principal", id: idNum });
          }}
        >
          View full profile &rarr;
        </button>
      )}
      {node.node_type === "registrant" && (
        <p className="group-card-note" style={{ marginTop: 8 }}>Click the node again to expand/collapse its contacts and contribution recipients.</p>
      )}
      {connected.length > 0 && (
        <>
          <h3 style={{ marginTop: 16 }}>Connections ({connected.length})</h3>
          {connected.slice(0, 30).map((e, i) => (
            <div className="field-block" key={i}>
              <div className="field-key">{e.edge_type}{e.edge_date ? ` · ${e.edge_date}` : ""}</div>
              <div className="field-text">
                {e.detail ?? "(no detail)"}
                {e.amount !== null && ` — $${e.amount.toLocaleString()}`}
              </div>
              {e.registrant_doc_id && (
                <button className="back-link" onClick={() => navigate({ kind: "document", id: e.registrant_doc_id! })}>
                  View source filing &rarr;
                </button>
              )}
            </div>
          ))}
        </>
      )}
    </div>
  );
}

export interface GraphViewHandle {
  /** Pans/zooms to a node by exact (case-insensitive) label match. Returns
   * whether a match is currently loaded — contact/recipient nodes only exist
   * once their registrant has been expanded. */
  focusByLabel: (label: string) => boolean;
}

export const GraphView = forwardRef<GraphViewHandle, { countryName: string; data: CountryGraph }>(
  function GraphView({ countryName, data }, ref) {
    const containerRef = useRef<HTMLDivElement>(null);
    const sigmaRef = useRef<Sigma | null>(null);
    const graphRef = useRef<Graph | null>(null);
    const hoveredRef = useRef<string | null>(null);
    const selectedIdRef = useRef<string | null>(null);
    const expandedRef = useRef<Set<string>>(new Set());
    const allEdgesRef = useRef<GraphEdge[]>(data.edges);
    const hiddenTypesRef = useRef<Set<GraphNodeType>>(new Set());
    const hoverEdgeRef = useRef<GraphEdge | null>(null);
    const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
    const [expandingId, setExpandingId] = useState<string | null>(null);
    const [hiddenTypes, setHiddenTypes] = useState<Set<GraphNodeType>>(new Set());
    const [tooltip, setTooltip] = useState<{ edge: GraphEdge; x: number; y: number } | null>(null);
    const [findQuery, setFindQuery] = useState("");
    const [findOpen, setFindOpen] = useState(false);

    useImperativeHandle(ref, () => ({
      focusByLabel: (label: string) => {
        const graph = graphRef.current;
        const renderer = sigmaRef.current;
        if (!graph || !renderer) return false;
        const target = label.trim().toLowerCase();
        let foundId: string | null = null;
        graph.forEachNode((id, attrs) => {
          if (foundId) return;
          if (((attrs.label as string) || "").trim().toLowerCase() === target) foundId = id;
        });
        if (!foundId) return false;
        selectedIdRef.current = foundId;
        setSelectedNode(focusNode(renderer, graph, foundId));
        renderer.refresh();
        return true;
      },
    }));

    useEffect(() => {
      hiddenTypesRef.current = hiddenTypes;
      sigmaRef.current?.refresh();
    }, [hiddenTypes]);

    useEffect(() => {
      if (!containerRef.current) return;
      const graph = buildBackboneGraph(data);
      graphRef.current = graph;
      allEdgesRef.current = data.edges;
      expandedRef.current = new Set();
      selectedIdRef.current = null;
      hoveredRef.current = null;
      hoverEdgeRef.current = null;
      setSelectedNode(null);
      setHiddenTypes(new Set());

      const renderer = new Sigma(graph, containerRef.current, {
        labelColor: { color: "#f5f2ec" },
        defaultDrawNodeHover: drawNodeHoverWithDarkLabel,
        defaultEdgeType: "arrow",
        edgeProgramClasses: { arrow: EdgeArrowProgram },
        enableEdgeEvents: true,
        nodeReducer: (node, attrs) => {
          const nodeType = attrs.nodeType as GraphNodeType;
          if (hiddenTypesRef.current.has(nodeType)) return { ...attrs, hidden: true };
          const showLabel = node === hoveredRef.current || node === selectedIdRef.current;
          return { ...attrs, label: showLabel ? attrs.label : undefined };
        },
        edgeReducer: (edge, attrs) => {
          const [source, target] = graph.extremities(edge);
          const sourceType = graph.getNodeAttribute(source, "nodeType") as GraphNodeType;
          const targetType = graph.getNodeAttribute(target, "nodeType") as GraphNodeType;
          if (hiddenTypesRef.current.has(sourceType) || hiddenTypesRef.current.has(targetType)) {
            return { ...attrs, hidden: true };
          }
          return attrs;
        },
      });
      sigmaRef.current = renderer;
      fitViewToNodes(renderer);

      renderer.on("enterNode", ({ node }) => { hoveredRef.current = node; renderer.refresh(); });
      renderer.on("leaveNode", () => { hoveredRef.current = null; renderer.refresh(); });
      renderer.on("enterEdge", ({ edge }) => { hoverEdgeRef.current = graph.getEdgeAttribute(edge, "raw") as GraphEdge; });
      renderer.on("leaveEdge", () => { hoverEdgeRef.current = null; setTooltip(null); });

      const onMouseMove = (e: MouseEvent) => {
        if (!hoverEdgeRef.current || !containerRef.current) return;
        const rect = containerRef.current.getBoundingClientRect();
        setTooltip({ edge: hoverEdgeRef.current, x: e.clientX - rect.left, y: e.clientY - rect.top });
      };
      containerRef.current.addEventListener("mousemove", onMouseMove);

      renderer.on("clickNode", async ({ node }) => {
        const attrs = graph.getNodeAttributes(node);
        selectedIdRef.current = node;
        setSelectedNode(attrs.raw as GraphNode);
        if (attrs.nodeType !== "registrant") return;

        if (expandedRef.current.has(node)) {
          // Collapse: drop this registrant's outgoing edges, then prune any
          // contact/recipient node left with no remaining edges (a node shared
          // with another still-expanded registrant survives).
          const toRemove = graph.filterOutEdges(node, (_, a) => a.edgeType !== "represents");
          toRemove.forEach((e) => graph.dropEdge(e));
          graph.forEachNode((n, a) => {
            if (!isBackbone(a.nodeType) && graph.degree(n) === 0) graph.dropNode(n);
          });
          resizeExpansionNodes(graph);
          expandedRef.current.delete(node);
          renderer.refresh();
          return;
        }

        setExpandingId(node);
        try {
          const registrantId = Number(node.split(":")[1]);
          const expansion = await api.expandRegistrant(countryName, registrantId);
          const newIds: string[] = [];
          for (const n of expansion.nodes) {
            if (!graph.hasNode(n.id)) {
              graph.addNode(n.id, {
                label: n.label, size: 4, color: NODE_COLOR[n.node_type], x: 0, y: 0,
                nodeType: n.node_type, raw: n,
              });
            }
            newIds.push(n.id);
          }
          placeInSpiral(graph, node, newIds);
          for (const e of expansion.edges) {
            if (graph.hasNode(e.source) && graph.hasNode(e.target)) {
              graph.addEdge(e.source, e.target, { size: 1, color: "#ffa300", edgeType: e.edge_type, raw: e });
            }
          }
          resizeExpansionNodes(graph);
          allEdgesRef.current = [...allEdgesRef.current, ...expansion.edges];
          expandedRef.current.add(node);
        } finally {
          setExpandingId(null);
          renderer.refresh();
        }
      });

      return () => {
        containerRef.current?.removeEventListener("mousemove", onMouseMove);
        renderer.kill();
        sigmaRef.current = null;
        graphRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [data, countryName]);

    useEffect(() => {
      sigmaRef.current?.refresh();
    }, [selectedNode]);

    if (data.nodes.length === 0) {
      return <div className="loading">No reportable-contact activity on file for this country.</div>;
    }

    const toggleType = (t: GraphNodeType) => {
      setHiddenTypes((prev) => {
        const next = new Set(prev);
        if (next.has(t)) next.delete(t); else next.add(t);
        return next;
      });
    };

    const findMatches: { id: string; label: string }[] = [];
    if (findOpen && findQuery.trim().length >= 2 && graphRef.current) {
      const q = findQuery.trim().toLowerCase();
      graphRef.current.forEachNode((id, attrs) => {
        if (findMatches.length >= 8) return;
        const label = (attrs.label as string) || "";
        if (label.toLowerCase().includes(q)) findMatches.push({ id, label });
      });
    }

    const selectFindMatch = (id: string) => {
      const graph = graphRef.current, renderer = sigmaRef.current;
      if (!graph || !renderer) return;
      selectedIdRef.current = id;
      setSelectedNode(focusNode(renderer, graph, id));
      renderer.refresh();
      setFindQuery("");
      setFindOpen(false);
    };

    return (
      <div>
        <p className="graph-caption">
          Hover a node to see its name. Click any registrant to reveal their reportable contacts and contribution
          recipients. Click a legend swatch to hide/show that node type.
        </p>

        <div className="graph-toolbar">
          <div className="graph-find">
            <input
              type="text"
              placeholder="Find in this graph…"
              value={findQuery}
              onChange={(e) => setFindQuery(e.target.value)}
              onFocus={() => setFindOpen(true)}
              onBlur={() => setTimeout(() => setFindOpen(false), 150)}
            />
            {findOpen && findQuery.trim().length >= 2 && (
              <ul className="graph-find-results">
                {findMatches.length === 0 ? (
                  <li className="search-no-results">No matches loaded</li>
                ) : (
                  findMatches.map((m) => (
                    <li key={m.id} onMouseDown={() => selectFindMatch(m.id)}>{m.label}</li>
                  ))
                )}
              </ul>
            )}
          </div>
          <div className="graph-controls">
            <button className="graph-control-btn" title="Zoom in" onClick={() => sigmaRef.current && zoomBy(sigmaRef.current, 0.7)}>+</button>
            <button className="graph-control-btn" title="Zoom out" onClick={() => sigmaRef.current && zoomBy(sigmaRef.current, 1 / 0.7)}>&minus;</button>
            <button className="graph-control-btn" title="Reset view" onClick={() => sigmaRef.current && resetView(sigmaRef.current)}>Reset</button>
          </div>
        </div>

        {data.omitted_registrant_count > 0 && (
          <span className="pill-note">
            +{data.omitted_registrant_count} more registrant{data.omitted_registrant_count === 1 ? "" : "s"} with less activity not shown
          </span>
        )}

        <div className="graph-canvas-wrap">
          <div ref={containerRef} className="graph-canvas" />
          {tooltip && (
            <div className="graph-tooltip" style={{ left: tooltip.x + 12, top: tooltip.y + 12 }}>
              <div className="graph-tooltip-type">
                {tooltip.edge.edge_type}{tooltip.edge.edge_date ? ` · ${tooltip.edge.edge_date}` : ""}
              </div>
              {tooltip.edge.detail && <div className="graph-tooltip-detail">{tooltip.edge.detail}</div>}
              {tooltip.edge.amount !== null && tooltip.edge.amount !== undefined && (
                <div className="graph-tooltip-detail">${tooltip.edge.amount.toLocaleString()}</div>
              )}
            </div>
          )}
        </div>
        {expandingId && <div className="row-meta" style={{ marginTop: 6 }}>Loading contacts…</div>}

        <div className="legend">
          {LEGEND_ORDER.map((t) => (
            <button
              key={t}
              className={`legend-item${hiddenTypes.has(t) ? " inactive" : ""}`}
              onClick={() => toggleType(t)}
              title="Click to hide/show"
            >
              <span className="dot" style={{ background: NODE_COLOR[t] }} />
              {LEGEND_LABEL[t]}
            </button>
          ))}
        </div>

        {selectedNode && <NodeDetail node={selectedNode} edges={allEdgesRef.current} />}
      </div>
    );
  },
);
