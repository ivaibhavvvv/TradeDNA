"use client";

/**
 * TradeDNA Phase 8C - Signature 5-Axis Spider Radar Chart Component.
 * Visualizes the quantitative fingerprint across Profitability, Risk Management,
 * Consistency, Discipline, and Execution Quality (0-100).
 */

import React, { useState } from "react";
import { cn } from "@/lib/utils";

interface SpiderRadarChartProps {
  dimensions?: {
    profitability: number;
    risk_management: number;
    consistency: number;
    discipline: number;
    execution_quality: number;
  };
  className?: string;
  size?: number;
}

export function SpiderRadarChart({
  dimensions = {
    profitability: 75,
    risk_management: 80,
    consistency: 68,
    discipline: 85,
    execution_quality: 72,
  },
  className,
  size = 320,
}: SpiderRadarChartProps) {
  const [hoveredAxis, setHoveredAxis] = useState<string | null>(null);

  const axes = [
    { key: "profitability", label: "Profitability", score: dimensions.profitability ?? 50 },
    { key: "risk_management", label: "Risk Management", score: dimensions.risk_management ?? 50 },
    { key: "consistency", label: "Consistency", score: dimensions.consistency ?? 50 },
    { key: "discipline", label: "Discipline", score: dimensions.discipline ?? 50 },
    { key: "execution_quality", label: "Execution Quality", score: dimensions.execution_quality ?? 50 },
  ];

  const center = size / 2;
  const radius = (size / 2) * 0.72;
  const numAxes = axes.length;
  const angleStep = (Math.PI * 2) / numAxes;

  // Concentric levels (20%, 40%, 60%, 80%, 100%)
  const levels = [0.2, 0.4, 0.6, 0.8, 1.0];

  // Polygon points
  const polygonPoints = axes.map((axis, i) => {
    const angle = i * angleStep - Math.PI / 2;
    const r = (axis.score / 100) * radius;
    const x = center + r * Math.cos(angle);
    const y = center + r * Math.sin(angle);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  return (
    <div className={cn("flex flex-col items-center justify-center space-y-3", className)}>
      <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
        <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-full select-none overflow-visible">
          <defs>
            <linearGradient id="radarGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#a855f7" stopOpacity="0.45" />
              <stop offset="50%" stopColor="#06b6d4" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.25" />
            </linearGradient>
          </defs>

          {/* Concentric Pentagon Grid Rings */}
          {levels.map((lvl, lIdx) => {
            const ringPoints = Array.from({ length: numAxes }).map((_, i) => {
              const angle = i * angleStep - Math.PI / 2;
              const r = lvl * radius;
              const x = center + r * Math.cos(angle);
              const y = center + r * Math.sin(angle);
              return `${x.toFixed(1)},${y.toFixed(1)}`;
            }).join(" ");

            return (
              <polygon
                key={lIdx}
                points={ringPoints}
                fill="none"
                stroke="#1e293b"
                strokeWidth={lIdx === levels.length - 1 ? "1.5" : "1"}
                strokeDasharray={lIdx === levels.length - 1 ? undefined : "3 3"}
              />
            );
          })}

          {/* Axis Radial Lines */}
          {axes.map((axis, i) => {
            const angle = i * angleStep - Math.PI / 2;
            const x = center + radius * Math.cos(angle);
            const y = center + radius * Math.sin(angle);
            return (
              <line
                key={i}
                x1={center}
                y1={center}
                x2={x}
                y2={y}
                stroke="#334155"
                strokeWidth="1"
              />
            );
          })}

          {/* Shaded Score Polygon */}
          <polygon
            points={polygonPoints}
            fill="url(#radarGrad)"
            stroke="#a855f7"
            strokeWidth="2.5"
            strokeLinejoin="round"
            className="transition-all duration-300"
          />

          {/* Score Vertex Dots & Axis Labels */}
          {axes.map((axis, i) => {
            const angle = i * angleStep - Math.PI / 2;
            const r = (axis.score / 100) * radius;
            const x = center + r * Math.cos(angle);
            const y = center + r * Math.sin(angle);

            const labelR = radius + 24;
            const labelX = center + labelR * Math.cos(angle);
            const labelY = center + labelR * Math.sin(angle);

            const isHovered = hoveredAxis === axis.key;

            return (
              <g
                key={axis.key}
                onMouseEnter={() => setHoveredAxis(axis.key)}
                onMouseLeave={() => setHoveredAxis(null)}
                className="cursor-pointer"
              >
                <circle
                  cx={x}
                  cy={y}
                  r={isHovered ? 6 : 4}
                  fill="#c084fc"
                  stroke="#0f172a"
                  strokeWidth="2"
                  className="transition-all duration-150"
                />
                <text
                  x={labelX}
                  y={labelY}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill={isHovered ? "#38bdf8" : "#94a3b8"}
                  fontSize="11"
                  fontWeight={isHovered ? "bold" : "medium"}
                  fontFamily="system-ui"
                >
                  {axis.label} ({axis.score})
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* Axis Score Pill Badges */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 w-full pt-2">
        {axes.map((a) => (
          <div
            key={a.key}
            className={cn(
              "flex justify-between items-center rounded-lg border px-2.5 py-1.5 text-xs transition-colors",
              hoveredAxis === a.key
                ? "border-purple-500/80 bg-purple-950/40 text-purple-200"
                : "border-slate-800 bg-slate-900/60 text-slate-300"
            )}
            onMouseEnter={() => setHoveredAxis(a.key)}
            onMouseLeave={() => setHoveredAxis(null)}
          >
            <span className="truncate pr-1">{a.label}:</span>
            <span className="font-mono font-bold text-cyan-400">{a.score}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
