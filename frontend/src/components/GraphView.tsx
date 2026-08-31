import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import { useEffect, useMemo, useRef, useState } from "react";
import { Sigma } from "sigma";
import type { CountryGraph, GraphEdge, GraphNode, GraphNodeType } from "../api/client";
import { useStore } from "../state/store";

const NODE_COLOR: Record<GraphNodeType, string> = {
  foreign_principal: "#ff4f00",
  registrant: "#4997d0",
  contact: "#ffa300",
  recipient: "#263d6b",
};

const NODE_SIZE: Record<GraphNodeType, number> = {
  foreign_principal: 8,
  registrant: 7,
  contact: 4,
  recipient: 4,
};

function buildGraph(data: CountryGraph): Graph {
  const graph = new Graph({ multi: true, type: "directed" });
  const degree = new Map<string, number>();
  for (const e of data.edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }

  for (const n of data.nodes) {
    const d = degree.get(n.id) ?? 0;
    graph.addNode(n.id, {
      label: n.label,
      size: NODE_SIZE[n.node_type] + Math.min(d, 10) * 0.6,
      color: NODE_COLOR[n.node_type],
      x: Math.random(),
      y: Math.random(),
      nodeType: n.node_type,
    });
  }
  for (const e of data.edges) {
    if (!graph.hasNode(e.source) || !graph.hasNode(e.target)) continue;
    graph.addEdge(e.source, e.target, {
      size: e.edge_type === "contributed" ? Math.min(2 + Math.log((e.amount ?? 1) + 1), 6) : 1,
      color: e.edge_type === "represents" ? "#8c8c8c" : e.edge_type === "contacted" ? "#ffa300" : "#263d6b",
      edgeType: e.edge_type,
    });
  }

  // barnesHutOptimize is not optional at this graph's real scale (a busy
  // country's reportable-contact network can be 1000+ nodes, e.g. China) —
  // without it, forceAtlas2's O(n^2) per-iteration cost freezes the tab for
  // several seconds on the main thread.
  if (graph.order > 1) {
    forceAtlas2.assign(graph, {
      iterations: graph.order > 300 ? 80 : 200,
      settings: { gravity: 1, scalingRatio: 10, barnesHutOptimize: graph.order > 200 },
    });
  }
  return graph;
}

function NodeDetail({ node, edges }: { node: GraphNode; edges: GraphEdge[] }) {
  const navigate = useStore((s) => s.navigate);
  const connected = edges.filter((e) => e.source === node.id || e.target === node.id);

  return (
    <div className="doc-body" style={{ marginTop: 16 }}>
      <h3>{node.node_type.replace(/_/g, " ")}</h3>
      <div className="record-title" style={{ fontSize: 18 }}>{node.label}</div>
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
      <h3 style={{ marginTop: 16 }}>Connections ({connected.length})</h3>
      {connected.map((e, i) => (
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
    </div>
  );
}

export function GraphView({ data }: { data: CountryGraph }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const graph = useMemo(() => buildGraph(data), [data]);
  const selectedNode = selectedId ? data.nodes.find((n) => n.id === selectedId) ?? null : null;

  useEffect(() => {
    if (!containerRef.current) return;
    const renderer = new Sigma(graph, containerRef.current, {
      labelColor: { color: "#f5f2ec" },
      defaultEdgeType: "line",
    });
    sigmaRef.current = renderer;
    renderer.on("clickNode", ({ node }) => setSelectedId(node));
    return () => {
      renderer.kill();
      sigmaRef.current = null;
    };
  }, [graph]);

  if (data.nodes.length === 0) {
    return <div className="loading">No graph data yet for this country.</div>;
  }

  return (
    <div>
      {data.truncated && (
        <div className="group-card-note" style={{ marginBottom: 10 }}>
          This network is large enough that it's been capped for display — not every node/edge is shown.
        </div>
      )}
      <div className="graph-container" ref={containerRef} style={{ height: 480, position: "relative", background: "var(--space)", borderRadius: 4, border: "1px solid var(--rule)" }} />
      <div className="legend" style={{ borderTop: "none", paddingLeft: 0 }}>
        <span><span className="dot" style={{ background: NODE_COLOR.foreign_principal }} />Foreign principal</span>
        <span><span className="dot" style={{ background: NODE_COLOR.registrant }} />Registrant</span>
        <span><span className="dot" style={{ background: NODE_COLOR.contact }} />Contact</span>
        <span><span className="dot" style={{ background: NODE_COLOR.recipient }} />Contribution recipient</span>
      </div>
      {selectedNode && <NodeDetail node={selectedNode} edges={data.edges} />}
    </div>
  );
}
