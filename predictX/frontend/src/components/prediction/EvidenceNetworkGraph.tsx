import { useEffect, useRef, useState } from 'react';
import type { Evidence, Prediction } from '../../types/market';

interface NetworkGraphProps {
  evidence: Evidence[];
  prediction: Prediction;
  ammPriceYes: number;
}

interface GraphNode {
  id: string;
  label: string;
  x: number;
  y: number;
  r: number;
  type: 'prediction' | 'market' | 'yes' | 'no' | 'neutral';
  detail?: string;
}

interface GraphEdge {
  from: string;
  to: string;
  type: 'yes' | 'no' | 'neutral' | 'market';
}

const NODE_COLORS = {
  prediction: { fill: '#6366f1', stroke: '#818cf8', glow: 'rgba(99,102,241,0.4)' },
  market:     { fill: '#3b82f6', stroke: '#60a5fa', glow: 'rgba(59,130,246,0.3)' },
  yes:        { fill: '#10b981', stroke: '#34d399', glow: 'rgba(16,185,129,0.3)' },
  no:         { fill: '#ef4444', stroke: '#f87171', glow: 'rgba(239,68,68,0.3)' },
  neutral:    { fill: '#6b7280', stroke: '#9ca3af', glow: 'rgba(107,114,128,0.3)' },
};

const EDGE_COLORS = {
  yes: '#34d399',
  no: '#f87171',
  neutral: '#6b7280',
  market: '#60a5fa',
};

function classifyEvidence(summary: string): 'yes' | 'no' | 'neutral' {
  const lower = summary.toLowerCase();
  const yesKeywords = ['yes', 'support', 'will', 'likely', 'positive', 'confirm', 'approve', 'agree', 'pass'];
  const noKeywords = ['no', 'against', 'unlikely', 'negative', 'deny', 'oppose', 'reject', 'fail', 'disagree'];
  const yScore = yesKeywords.filter(k => lower.includes(k)).length;
  const nScore = noKeywords.filter(k => lower.includes(k)).length;
  if (yScore > nScore) return 'yes';
  if (nScore > yScore) return 'no';
  return 'neutral';
}

function buildGraph(evidence: Evidence[], prediction: Prediction, ammPriceYes: number): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const W = 440;
  const H = 320;
  const cx = W / 2;
  const cy = H / 2;

  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];

  // Central prediction node
  const yesP = Math.round(prediction.probability_yes * 100);
  nodes.push({
    id: 'pred',
    label: `AI ${yesP}%`,
    x: cx,
    y: cy,
    r: 28,
    type: 'prediction',
    detail: `Confidence: ${Math.round(prediction.confidence * 100)}%`,
  });

  // Market price node
  const mktP = Math.round(ammPriceYes * 100);
  nodes.push({
    id: 'market',
    label: `Mkt ${mktP}%`,
    x: cx,
    y: 36,
    r: 20,
    type: 'market',
  });
  edges.push({ from: 'market', to: 'pred', type: 'market' });

  // Evidence nodes arranged in arc below center
  if (evidence.length > 0) {
    const count = evidence.length;
    const arcStart = Math.PI * 0.25;
    const arcEnd = Math.PI * 0.75;
    const radiusX = 160;
    const radiusY = 110;

    evidence.forEach((ev, i) => {
      const t = count === 1 ? 0.5 : i / (count - 1);
      const angle = arcStart + t * (arcEnd - arcStart);
      const x = cx + Math.cos(angle) * radiusX * (i % 2 === 0 ? 1 : -1);
      const y = cy + Math.sin(angle) * radiusY;

      const direction = classifyEvidence(ev.summary);
      const id = `ev-${i}`;
      const summaryShort = ev.summary.length > 24 ? ev.summary.slice(0, 22) + '..' : ev.summary;

      nodes.push({
        id,
        label: `E${i + 1}`,
        x: Math.max(24, Math.min(W - 24, x)),
        y: Math.max(24, Math.min(H - 24, y)),
        r: 16,
        type: direction,
        detail: summaryShort,
      });
      edges.push({ from: id, to: 'pred', type: direction });
    });
  }

  return { nodes, edges };
}

export default function EvidenceNetworkGraph({ evidence, prediction, ammPriceYes }: NetworkGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    // Trigger entrance animation
    const t = setTimeout(() => setMounted(true), 50);
    return () => clearTimeout(t);
  }, []);

  const { nodes, edges } = buildGraph(evidence, prediction, ammPriceYes);

  const nodeMap = new Map(nodes.map(n => [n.id, n]));

  return (
    <div className="rounded-xl bg-slate-900/60 border border-slate-700/40 p-3 overflow-hidden">
      <div className="flex items-center gap-2 mb-2">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#818cf8" strokeWidth="2" strokeLinecap="round">
          <circle cx="12" cy="5" r="3" />
          <circle cx="5" cy="19" r="3" />
          <circle cx="19" cy="19" r="3" />
          <line x1="12" y1="8" x2="5" y2="16" />
          <line x1="12" y1="8" x2="19" y2="16" />
        </svg>
        <span className="text-xs font-medium text-indigo-300">Evidence Network</span>
        <div className="flex-1" />
        <div className="flex items-center gap-3 text-[10px] text-slate-500">
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> YES
          </span>
          <span className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-rose-500 inline-block" /> NO
          </span>
        </div>
      </div>

      <svg
        ref={svgRef}
        viewBox="0 0 440 320"
        className="w-full"
        style={{ maxHeight: 280 }}
      >
        <defs>
          {/* Glow filters for each type */}
          {Object.entries(NODE_COLORS).map(([type, { glow }]) => (
            <filter key={type} id={`glow-${type}`} x="-50%" y="-50%" width="200%" height="200%">
              <feDropShadow dx="0" dy="0" stdDeviation="4" floodColor={glow} />
            </filter>
          ))}
          {/* Animated dash pattern */}
          <pattern id="dash-anim" patternUnits="userSpaceOnUse" width="12" height="1">
            <line x1="0" y1="0" x2="6" y2="0" stroke="white" strokeWidth="1" opacity="0.5">
              <animate attributeName="x1" from="0" to="12" dur="1.5s" repeatCount="indefinite" />
              <animate attributeName="x2" from="6" to="18" dur="1.5s" repeatCount="indefinite" />
            </line>
          </pattern>
        </defs>

        {/* Edges */}
        {edges.map((edge, i) => {
          const from = nodeMap.get(edge.from);
          const to = nodeMap.get(edge.to);
          if (!from || !to) return null;
          const isHighlight = hoveredNode === edge.from || hoveredNode === edge.to;
          const color = EDGE_COLORS[edge.type];

          return (
            <g key={`edge-${i}`}>
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke={color}
                strokeWidth={isHighlight ? 2 : 1}
                opacity={mounted ? (isHighlight ? 0.8 : 0.3) : 0}
                className="transition-all duration-500"
              />
              {/* Animated particle along edge */}
              {mounted && (
                <circle r="2" fill={color} opacity="0.7">
                  <animateMotion
                    dur={`${2 + i * 0.3}s`}
                    repeatCount="indefinite"
                    path={`M${from.x},${from.y} L${to.x},${to.y}`}
                  />
                </circle>
              )}
            </g>
          );
        })}

        {/* Nodes */}
        {nodes.map(node => {
          const colors = NODE_COLORS[node.type];
          const isHovered = hoveredNode === node.id;
          const scale = mounted ? 1 : 0;
          const r = isHovered ? node.r + 3 : node.r;

          return (
            <g
              key={node.id}
              onMouseEnter={() => setHoveredNode(node.id)}
              onMouseLeave={() => setHoveredNode(null)}
              style={{
                transform: `translate(${node.x}px, ${node.y}px) scale(${scale})`,
                transformOrigin: `${node.x}px ${node.y}px`,
                transition: 'transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)',
                transitionDelay: node.type === 'prediction' ? '0.1s' : node.type === 'market' ? '0.2s' : `${0.3 + Math.random() * 0.3}s`,
                cursor: 'pointer',
              }}
            >
              {/* Outer glow ring on hover */}
              {isHovered && (
                <circle
                  cx={0}
                  cy={0}
                  r={r + 6}
                  fill="none"
                  stroke={colors.stroke}
                  strokeWidth="1"
                  opacity="0.4"
                >
                  <animate attributeName="r" from={r + 4} to={r + 10} dur="1s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="0.4" to="0" dur="1s" repeatCount="indefinite" />
                </circle>
              )}

              {/* Node circle */}
              <circle
                cx={0}
                cy={0}
                r={r}
                fill={colors.fill}
                stroke={colors.stroke}
                strokeWidth={isHovered ? 2.5 : 1.5}
                filter={`url(#glow-${node.type})`}
                className="transition-all duration-200"
              />

              {/* Pulse animation for prediction node */}
              {node.type === 'prediction' && mounted && (
                <circle cx={0} cy={0} r={r} fill="none" stroke={colors.stroke} strokeWidth="1" opacity="0">
                  <animate attributeName="r" from={r} to={r + 12} dur="2s" repeatCount="indefinite" />
                  <animate attributeName="opacity" from="0.5" to="0" dur="2s" repeatCount="indefinite" />
                </circle>
              )}

              {/* Label */}
              <text
                x={0}
                y={1}
                textAnchor="middle"
                dominantBaseline="middle"
                fill="white"
                style={{ fontSize: node.type === 'prediction' ? '10px' : '9px', fontWeight: 600, userSelect: 'none' }}
              >
                {node.label}
              </text>

              {/* Tooltip on hover */}
              {isHovered && node.detail && (
                <g>
                  <rect
                    x={-60}
                    y={-r - 28}
                    width={120}
                    height={20}
                    rx={6}
                    fill="rgba(15,23,42,0.92)"
                    stroke={colors.stroke}
                    strokeWidth="0.5"
                  />
                  <text
                    x={0}
                    y={-r - 15}
                    textAnchor="middle"
                    fill="#e2e8f0"
                    style={{ fontSize: '8px', userSelect: 'none' }}
                  >
                    {node.detail}
                  </text>
                </g>
              )}
            </g>
          );
        })}

        {/* "No evidence" placeholder */}
        {evidence.length === 0 && (
          <text x={220} y={240} textAnchor="middle" fill="#475569" style={{ fontSize: '11px' }}>
            No evidence submitted yet
          </text>
        )}
      </svg>
    </div>
  );
}
