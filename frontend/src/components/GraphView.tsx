import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { useEffect, useRef, useState } from "react";
import { Sigma } from "sigma";
import { api, type CountryGraph, type GraphEdge, type GraphNode, type GraphNodeType } from "../api/client";
import { useStore } from "../state/store";

const NODE_COLOR: Record<GraphNodeType, string> = {
  foreign_principal: "#ff4f00",
  registrant: "#4997d0",
  contact: "#ffa300",
  recipient: "#263d6b",
};

const BACKBONE_SIZE: Record<"foreign_principal" | "registrant", number> = {
  foreign_principal: 6,
  registrant: 6,
};

// Backbone nodes (registrant/foreign_principal, always ≤150 — a genuinely legible
// count) keep always-on labels; expanded contact/recipient nodes only label on
// hover or when selected, since those are the noisy raw-text entities (docs/phase2.md).
function isBackbone(nodeType: GraphNodeType): boolean {
  return nodeType === "registrant" || nodeType === "foreign_principal";
}

function registrantSize(node: GraphNode): number {
  const activity = (node.contact_count ?? 0) + (node.contribution_count ?? 0);
  return BACKBONE_SIZE.registrant + Math.min(Math.sqrt(activity), 12);
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
  for (const n of data.nodes) {
    graph.addNode(n.id, {
      label: n.label,
      size: n.node_type === "registrant" ? registrantSize(n) : BACKBONE_SIZE.foreign_principal,
      color: NODE_COLOR[n.node_type],
      x: Math.random(),
      y: Math.random(),
      nodeType: n.node_type,
      raw: n,
    });
  }
  for (const e of data.edges) {
    if (graph.hasNode(e.source) && graph.hasNode(e.target)) {
      graph.addEdge(e.source, e.target, { size: 1.5, color: "#c8c8c8", edgeType: e.edge_type });
    }
  }
  if (graph.order > 1) {
    forceAtlas2.assign(graph, { iterations: 250, settings: { gravity: 1, scalingRatio: 12 } });
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

// New nodes from an expansion land in a small ring around the registrant that
// was clicked, rather than a global forceAtlas2 re-run — re-laying out the
// whole graph on every click would reshuffle everything the user just got
// oriented to.
function placeInRing(graph: Graph, centerId: string, newNodeIds: string[]): void {
  const cx = graph.getNodeAttribute(centerId, "x");
  const cy = graph.getNodeAttribute(centerId, "y");
  const radius = 0.06;
  newNodeIds.forEach((id, i) => {
    const angle = (2 * Math.PI * i) / Math.max(newNodeIds.length, 1);
    graph.setNodeAttribute(id, "x", cx + radius * Math.cos(angle));
    graph.setNodeAttribute(id, "y", cy + radius * Math.sin(angle));
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

export function GraphView({ countryName, data }: { countryName: string; data: CountryGraph }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const hoveredRef = useRef<string | null>(null);
  const selectedIdRef = useRef<string | null>(null);
  const expandedRef = useRef<Set<string>>(new Set());
  const allEdgesRef = useRef<GraphEdge[]>(data.edges);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [expandingId, setExpandingId] = useState<string | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const graph = buildBackboneGraph(data);
    graphRef.current = graph;
    allEdgesRef.current = data.edges;
    expandedRef.current = new Set();
    selectedIdRef.current = null;
    hoveredRef.current = null;
    setSelectedNode(null);

    const renderer = new Sigma(graph, containerRef.current, {
      labelColor: { color: "#f5f2ec" },
      defaultEdgeType: "line",
      nodeReducer: (node, attrs) => {
        const nodeType = attrs.nodeType as GraphNodeType;
        const showLabel = isBackbone(nodeType) || node === hoveredRef.current || node === selectedIdRef.current;
        return { ...attrs, label: showLabel ? attrs.label : undefined };
      },
    });
    sigmaRef.current = renderer;
    fitViewToNodes(renderer);

    renderer.on("enterNode", ({ node }) => { hoveredRef.current = node; renderer.refresh(); });
    renderer.on("leaveNode", () => { hoveredRef.current = null; renderer.refresh(); });

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
        placeInRing(graph, node, newIds);
        for (const e of expansion.edges) {
          if (graph.hasNode(e.source) && graph.hasNode(e.target)) {
            graph.addEdge(e.source, e.target, { size: 1, color: "#ffa300", edgeType: e.edge_type });
          }
        }
        allEdgesRef.current = [...allEdgesRef.current, ...expansion.edges];
        expandedRef.current.add(node);
      } finally {
        setExpandingId(null);
        renderer.refresh();
      }
    });

    return () => {
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

  return (
    <div>
      {data.omitted_registrant_count > 0 && (
        <div className="group-card-note" style={{ marginBottom: 10 }}>
          +{data.omitted_registrant_count} more registrant{data.omitted_registrant_count === 1 ? "" : "s"} with less
          activity not shown.
        </div>
      )}
      <div
        ref={containerRef}
        style={{ height: 480, position: "relative", background: "var(--space)", borderRadius: 4, border: "1px solid var(--rule)" }}
      />
      {expandingId && <div className="row-meta" style={{ marginTop: 6 }}>Loading contacts…</div>}
      <div className="legend" style={{ borderTop: "none", paddingLeft: 0 }}>
        <span><span className="dot" style={{ background: NODE_COLOR.foreign_principal }} />Foreign principal</span>
        <span><span className="dot" style={{ background: NODE_COLOR.registrant }} />Registrant (size = activity, click to expand)</span>
        <span><span className="dot" style={{ background: NODE_COLOR.contact }} />Contact</span>
        <span><span className="dot" style={{ background: NODE_COLOR.recipient }} />Contribution recipient</span>
      </div>
      {selectedNode && <NodeDetail node={selectedNode} edges={allEdgesRef.current} />}
    </div>
  );
}
