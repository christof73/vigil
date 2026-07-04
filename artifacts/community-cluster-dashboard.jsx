import React, { useState, useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  Cell,
} from "recharts";
import {
  TrendingUp, TrendingDown, Minus, AlertTriangle, Eye, MessageSquare,
  ArrowUpRight, ChevronDown, ChevronRight, Filter, Zap, BookOpen,
  CheckCircle2, XCircle, Clock, Shield, Layers, Activity,
} from "lucide-react";

// ── Mock data seeded from actual taxonomy.yaml ───────────────────────────

const LANES = {
  grc:              { label: "GRC",              weight: 1.3, color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
  secops:           { label: "SecOps",           weight: 1.0, color: "#ef4444", bg: "rgba(239,68,68,0.12)" },
  platform_utility: { label: "Platform Utility", weight: 1.0, color: "#3b82f6", bg: "rgba(59,130,246,0.12)" },
  hrsd:             { label: "HRSD",             weight: 0.9, color: "#8b5cf6", bg: "rgba(139,92,246,0.12)" },
  itsm:             { label: "ITSM",             weight: 0.7, color: "#06b6d4", bg: "rgba(6,182,212,0.12)" },
  other:            { label: "Other",            weight: 0.6, color: "#64748b", bg: "rgba(100,116,139,0.12)" },
};

const CLUSTERS = [
  { slug: "grc_evidence_collection", label: "GRC Evidence Collection & Requests",     lane: "grc",              composite: 0.7215, thread_count: 67, unsolved_rate: 0.82, workaround_rate: 0.22, commercial_rate: 0.12, store_gap: 0.85, delta: +0.041, outlier: true,  promoted: true,  opp_status: "watching" },
  { slug: "grc_control_testing",     label: "Control Test Management",                lane: "grc",              composite: 0.6380, thread_count: 48, unsolved_rate: 0.71, workaround_rate: 0.18, commercial_rate: 0.09, store_gap: 0.70, delta: +0.018, outlier: false, promoted: false, opp_status: null },
  { slug: "update_set_lifecycle",    label: "Update Set Promotion & Dependencies",    lane: "platform_utility", composite: 0.5920, thread_count: 89, unsolved_rate: 0.65, workaround_rate: 0.31, commercial_rate: 0.05, store_gap: 0.40, delta: -0.012, outlier: true,  promoted: false, opp_status: null },
  { slug: "flow_designer_pain",      label: "Flow Designer Errors & Limits",          lane: "platform_utility", composite: 0.5740, thread_count: 72, unsolved_rate: 0.69, workaround_rate: 0.25, commercial_rate: 0.07, store_gap: 0.50, delta: +0.032, outlier: true,  promoted: false, opp_status: null },
  { slug: "grc_audit_engagement",    label: "Audit Engagement Workflow",              lane: "grc",              composite: 0.5610, thread_count: 34, unsolved_rate: 0.71, workaround_rate: 0.15, commercial_rate: 0.08, store_gap: 0.70, delta: null,   outlier: false, promoted: false, opp_status: null },
  { slug: "acl_debugging",           label: "ACL & Access Control Debugging",         lane: "platform_utility", composite: 0.5280, thread_count: 61, unsolved_rate: 0.59, workaround_rate: 0.20, commercial_rate: 0.04, store_gap: 0.35, delta: -0.005, outlier: false, promoted: false, opp_status: null },
  { slug: "scoped_app_gotchas",      label: "Scoped App Development Quirks",          lane: "platform_utility", composite: 0.5120, thread_count: 55, unsolved_rate: 0.62, workaround_rate: 0.28, commercial_rate: 0.06, store_gap: 0.45, delta: +0.008, outlier: false, promoted: false, opp_status: null },
  { slug: "secops_vr_sir",           label: "Security Incident & Vulnerability Response", lane: "secops",       composite: 0.4980, thread_count: 38, unsolved_rate: 0.74, workaround_rate: 0.13, commercial_rate: 0.11, store_gap: 0.60, delta: +0.022, outlier: false, promoted: false, opp_status: null },
  { slug: "oscal_fedramp",           label: "OSCAL / FedRAMP Machine-Readable",       lane: "grc",              composite: 0.4870, thread_count: 22, unsolved_rate: 0.86, workaround_rate: 0.09, commercial_rate: 0.18, store_gap: 0.90, delta: +0.055, outlier: false, promoted: true,  opp_status: "evaluating" },
  { slug: "clone_management",        label: "Clone Exclusions & Data Preservation",   lane: "platform_utility", composite: 0.4650, thread_count: 44, unsolved_rate: 0.55, workaround_rate: 0.16, commercial_rate: 0.03, store_gap: 0.30, delta: -0.018, outlier: false, promoted: false, opp_status: null },
  { slug: "grc_entity_scoping",      label: "Entity & Profile Scoping",              lane: "grc",              composite: 0.4420, thread_count: 19, unsolved_rate: 0.79, workaround_rate: 0.11, commercial_rate: 0.05, store_gap: 0.65, delta: +0.010, outlier: false, promoted: false, opp_status: null },
  { slug: "data_isolation",          label: "Multi-Org Data Isolation",               lane: "platform_utility", composite: 0.4310, thread_count: 31, unsolved_rate: 0.61, workaround_rate: 0.19, commercial_rate: 0.10, store_gap: 0.55, delta: null,   outlier: false, promoted: false, opp_status: null },
  { slug: "import_transform",        label: "Import Sets & Transform Maps",           lane: "platform_utility", composite: 0.4180, thread_count: 52, unsolved_rate: 0.52, workaround_rate: 0.23, commercial_rate: 0.03, store_gap: 0.25, delta: -0.007, outlier: false, promoted: false, opp_status: null },
  { slug: "grc_migration",           label: "GRC Cross-Instance Migration",           lane: "grc",              composite: 0.4050, thread_count: 15, unsolved_rate: 0.80, workaround_rate: 0.07, commercial_rate: 0.13, store_gap: 0.75, delta: +0.029, outlier: false, promoted: false, opp_status: null },
  { slug: "deployment_validation",   label: "Pre-Deployment Validation",              lane: "platform_utility", composite: 0.3920, thread_count: 37, unsolved_rate: 0.54, workaround_rate: 0.14, commercial_rate: 0.02, store_gap: 0.20, delta: -0.003, outlier: false, promoted: false, opp_status: null },
  { slug: "notifications_email",     label: "Notification & Email Delivery",          lane: "platform_utility", composite: 0.3780, thread_count: 41, unsolved_rate: 0.51, workaround_rate: 0.12, commercial_rate: 0.02, store_gap: 0.15, delta: -0.011, outlier: false, promoted: false, opp_status: null },
  { slug: "service_portal_uib",      label: "Service Portal / UI Builder / Workspaces", lane: "platform_utility", composite: 0.3650, thread_count: 58, unsolved_rate: 0.48, workaround_rate: 0.20, commercial_rate: 0.04, store_gap: 0.10, delta: +0.002, outlier: false, promoted: false, opp_status: null },
  { slug: "integrations_rest",       label: "Integrations, REST & MID Server",        lane: "platform_utility", composite: 0.3510, thread_count: 63, unsolved_rate: 0.45, workaround_rate: 0.17, commercial_rate: 0.03, store_gap: 0.10, delta: -0.004, outlier: false, promoted: false, opp_status: null },
  { slug: "grc_reporting",           label: "GRC Reporting & Dashboards",             lane: "grc",              composite: 0.3480, thread_count: 18, unsolved_rate: 0.67, workaround_rate: 0.06, commercial_rate: 0.06, store_gap: 0.50, delta: +0.015, outlier: false, promoted: false, opp_status: null },
  { slug: "hrsd_case_mgmt",          label: "HR Case & Lifecycle Management",         lane: "hrsd",             composite: 0.3310, thread_count: 29, unsolved_rate: 0.62, workaround_rate: 0.10, commercial_rate: 0.07, store_gap: 0.45, delta: null,   outlier: false, promoted: false, opp_status: null },
  { slug: "itsm_workflow",           label: "ITSM Workflow & SLA",                    lane: "itsm",             composite: 0.3100, thread_count: 95, unsolved_rate: 0.42, workaround_rate: 0.15, commercial_rate: 0.02, store_gap: 0.05, delta: -0.020, outlier: false, promoted: false, opp_status: null },
  { slug: "performance_tuning",      label: "Instance Performance & Large Tables",    lane: "platform_utility", composite: 0.2980, thread_count: 33, unsolved_rate: 0.58, workaround_rate: 0.24, commercial_rate: 0.01, store_gap: 0.20, delta: +0.006, outlier: false, promoted: false, opp_status: null },
  { slug: "cmdb_data_quality",       label: "CMDB Data Quality & Identification",     lane: "platform_utility", composite: 0.2850, thread_count: 40, unsolved_rate: 0.50, workaround_rate: 0.10, commercial_rate: 0.02, store_gap: 0.10, delta: -0.009, outlier: false, promoted: false, opp_status: null },
  { slug: "reporting_analytics",     label: "Reporting & Performance Analytics",      lane: "platform_utility", composite: 0.2710, thread_count: 27, unsolved_rate: 0.56, workaround_rate: 0.07, commercial_rate: 0.04, store_gap: 0.15, delta: +0.003, outlier: false, promoted: false, opp_status: null },
  { slug: "upgrade_release",         label: "Upgrades, Patching & Deprecations",      lane: "platform_utility", composite: 0.2540, thread_count: 46, unsolved_rate: 0.43, workaround_rate: 0.09, commercial_rate: 0.01, store_gap: 0.05, delta: -0.014, outlier: false, promoted: false, opp_status: null },
];

const UNCATEGORIZED = { count: 142, total: 1198, pct: 11.9 };

const CONTENT_CANDIDATES = [
  { slug: "grc_evidence_collection", label: "GRC Evidence Collection", unsolved_rate: 0.82, high_view_threads: 12 },
  { slug: "flow_designer_pain",      label: "Flow Designer Errors",   unsolved_rate: 0.69, high_view_threads: 9 },
  { slug: "update_set_lifecycle",    label: "Update Set Promotion",   unsolved_rate: 0.65, high_view_threads: 15 },
  { slug: "scoped_app_gotchas",      label: "Scoped App Quirks",      unsolved_rate: 0.62, high_view_threads: 7 },
  { slug: "acl_debugging",           label: "ACL Debugging",          unsolved_rate: 0.59, high_view_threads: 8 },
];

const DIGEST_DATE = "2026-07-01";
const WINDOW = "2025-07-01 → 2026-07-01";

// ── Utility ──────────────────────────────────────────────────────────────

const fmt = (n, d = 2) => n == null ? "—" : n.toFixed(d);
const pct = (n) => n == null ? "—" : `${(n * 100).toFixed(0)}%`;

const useIsMobile = () => {
  const [m, setM] = useState(window.innerWidth < 640);
  React.useEffect(() => {
    const h = () => setM(window.innerWidth < 640);
    window.addEventListener("resize", h);
    return () => window.removeEventListener("resize", h);
  }, []);
  return m;
};

// ── Components ───────────────────────────────────────────────────────────

function LaneBadge({ lane }) {
  const l = LANES[lane] || LANES.other;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      fontSize: 9, fontWeight: 600, letterSpacing: "0.5px",
      textTransform: "uppercase",
      color: l.color, background: l.bg,
      border: `1px solid ${l.color}28`,
      borderRadius: 999, padding: "2px 8px",
    }}>
      {l.label}
    </span>
  );
}

function DeltaBadge({ delta }) {
  if (delta == null) return <span style={{ color: "#475569", fontSize: 10 }}>NEW</span>;
  const up = delta > 0;
  const flat = Math.abs(delta) < 0.002;
  const Icon = flat ? Minus : up ? TrendingUp : TrendingDown;
  const color = flat ? "#475569" : up ? "#10b981" : "#ef4444";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 3, color, fontSize: 11, fontWeight: 500 }}>
      <Icon size={12} />
      {flat ? "—" : (up ? "+" : "") + delta.toFixed(3)}
    </span>
  );
}

function StatusBadge({ status }) {
  if (!status) return null;
  const colors = {
    watching: { c: "#06b6d4", bg: "rgba(6,182,212,0.12)" },
    evaluating: { c: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
    pursuing: { c: "#10b981", bg: "rgba(16,185,129,0.12)" },
    won: { c: "#10b981", bg: "rgba(16,185,129,0.18)" },
    lost: { c: "#ef4444", bg: "rgba(239,68,68,0.12)" },
    abandoned: { c: "#64748b", bg: "rgba(100,116,139,0.12)" },
  };
  const s = colors[status] || colors.watching;
  return (
    <span style={{
      fontSize: 9, fontWeight: 600, textTransform: "uppercase",
      letterSpacing: "0.5px", color: s.c, background: s.bg,
      border: `1px solid ${s.c}28`, borderRadius: 999, padding: "2px 8px",
    }}>
      {status}
    </span>
  );
}

function ScoreBar({ value, max = 1, color = "#3b82f6", width = 80 }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width, height: 4, background: "#1e293b", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: `${(value / max) * 100}%`, height: "100%", background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 10, color: "#94a3b8", fontVariantNumeric: "tabular-nums" }}>{fmt(value, 4)}</span>
    </div>
  );
}

function FactorRow({ label, value, color, maxValue = 1 }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 6 }}>
      <span style={{ fontSize: 10, color: "#94a3b8", minWidth: 100 }}>{label}</span>
      <div style={{ flex: 1, height: 3, background: "#1e293b", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: `${(value / maxValue) * 100}%`, height: "100%", background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 10, color: "#e2e8f0", fontVariantNumeric: "tabular-nums", minWidth: 36, textAlign: "right" }}>
        {typeof value === "number" && value <= 1 ? pct(value) : value}
      </span>
    </div>
  );
}

function ClusterCard({ cluster, selected, onClick }) {
  const lane = LANES[cluster.lane] || LANES.other;
  const isActive = selected?.slug === cluster.slug;
  return (
    <div
      onClick={() => onClick(cluster)}
      style={{
        background: isActive ? `${lane.bg}` : "#0c0c14",
        border: `1px solid ${isActive ? lane.color : "#1e293b"}`,
        borderTop: isActive ? `2px solid ${lane.color}` : "1px solid #1e293b",
        borderRadius: 10, padding: "12px 14px", cursor: "pointer",
        transition: "border-color 0.15s",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11, color: "#475569", fontVariantNumeric: "tabular-nums" }}>#{cluster.rank}</span>
          <LaneBadge lane={cluster.lane} />
          {cluster.outlier && (
            <span title="Outlier override" style={{ display: "inline-flex", color: "#f59e0b" }}>
              <Zap size={12} />
            </span>
          )}
          {cluster.promoted && <StatusBadge status={cluster.opp_status} />}
        </div>
        <DeltaBadge delta={cluster.delta} />
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: "#e2e8f0", marginBottom: 8, lineHeight: 1.3 }}>
        {cluster.label}
      </div>
      <div style={{ display: "flex", gap: 14, fontSize: 10, color: "#94a3b8" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
          <MessageSquare size={10} /> {cluster.thread_count}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
          <XCircle size={10} color={cluster.unsolved_rate > 0.7 ? "#ef4444" : "#94a3b8"} />
          {pct(cluster.unsolved_rate)} unsolved
        </span>
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {fmt(cluster.composite, 4)}
        </span>
      </div>
    </div>
  );
}

function DetailPanel({ cluster, onClose, isMobile }) {
  if (!cluster) return null;
  const lane = LANES[cluster.lane] || LANES.other;

  const radarData = [
    { factor: "Threads", value: cluster.thread_count / 95, fullMark: 1 },
    { factor: "Unsolved", value: cluster.unsolved_rate, fullMark: 1 },
    { factor: "Workaround", value: cluster.workaround_rate, fullMark: 1 },
    { factor: "Commercial", value: cluster.commercial_rate, fullMark: 1 },
    { factor: "Store Gap", value: cluster.store_gap ?? 0.5, fullMark: 1 },
  ];

  const content = (
    <div style={{ padding: isMobile ? "16px" : "0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <LaneBadge lane={cluster.lane} />
            {cluster.outlier && (
              <span style={{ fontSize: 9, color: "#f59e0b", fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase" }}>
                OUTLIER OVERRIDE
              </span>
            )}
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#e2e8f0", lineHeight: 1.3 }}>
            {cluster.label}
          </div>
          <div style={{ fontSize: 10, color: "#475569", marginTop: 4, fontFamily: "monospace" }}>
            {cluster.slug}
          </div>
        </div>
        {isMobile && (
          <button onClick={onClose} style={{ background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: 18 }}>×</button>
        )}
      </div>

      {/* Composite Score */}
      <div style={{
        background: "#0a0a0f", border: "1px solid #1e293b", borderRadius: 8, padding: 12, marginBottom: 12,
      }}>
        <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 6 }}>
          COMPOSITE SCORE
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <span style={{ fontSize: 28, fontWeight: 700, color: lane.color, fontVariantNumeric: "tabular-nums" }}>
            {fmt(cluster.composite, 4)}
          </span>
          <DeltaBadge delta={cluster.delta} />
        </div>
        <div style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>
          Lane weight: ×{lane.weight} • {lane.label}
        </div>
      </div>

      {/* Factor Breakdown */}
      <div style={{
        background: "#0a0a0f", border: "1px solid #1e293b", borderRadius: 8, padding: 12, marginBottom: 12,
      }}>
        <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 10 }}>
          SCORING FACTORS
        </div>
        <FactorRow label="Thread count" value={cluster.thread_count} color="#3b82f6" maxValue={95} />
        <FactorRow label="Unsolved rate" value={cluster.unsolved_rate} color={cluster.unsolved_rate > 0.7 ? "#ef4444" : "#f59e0b"} />
        <FactorRow label="Workaround rate" value={cluster.workaround_rate} color="#8b5cf6" />
        <FactorRow label="Commercial rate" value={cluster.commercial_rate} color="#ec4899" />
        <FactorRow label="Store gap" value={cluster.store_gap} color="#10b981" />
      </div>

      {/* Radar */}
      <div style={{
        background: "#0a0a0f", border: "1px solid #1e293b", borderRadius: 8, padding: 12, marginBottom: 12,
      }}>
        <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 4 }}>
          FACTOR PROFILE
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
            <PolarGrid stroke="#1e293b" />
            <PolarAngleAxis dataKey="factor" tick={{ fill: "#64748b", fontSize: 9 }} />
            <PolarRadiusAxis tick={false} axisLine={false} />
            <Radar dataKey="value" stroke={lane.color} fill={lane.color} fillOpacity={0.2} strokeWidth={1.5} />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Promotion Status */}
      <div style={{
        background: "#0a0a0f", border: "1px solid #1e293b", borderRadius: 8, padding: 12,
      }}>
        <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>
          PROMOTION STATUS
        </div>
        {cluster.promoted ? (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <CheckCircle2 size={14} color="#10b981" />
              <span style={{ fontSize: 11, color: "#10b981", fontWeight: 600 }}>Promoted to pipeline</span>
            </div>
            <div style={{ fontSize: 10, color: "#94a3b8" }}>
              Opportunity status: <StatusBadge status={cluster.opp_status} />
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Clock size={14} color="#64748b" />
            <span style={{ fontSize: 11, color: "#64748b" }}>Not promoted — awaiting human disposition</span>
          </div>
        )}
      </div>
    </div>
  );

  if (isMobile) {
    return (
      <div style={{
        position: "fixed", bottom: 0, left: 0, right: 0,
        background: "#0c0c14", borderTop: `2px solid ${lane.color}`,
        borderRadius: "16px 16px 0 0", maxHeight: "70vh", overflowY: "auto",
        zIndex: 100, boxShadow: "0 -8px 32px rgba(0,0,0,0.6)",
      }}>
        <div style={{ width: 32, height: 4, background: "#27273a", borderRadius: 2, margin: "8px auto" }} />
        {content}
      </div>
    );
  }

  return (
    <div style={{
      position: "sticky", top: 16,
      background: "#0c0c14", border: "1px solid #1e293b", borderRadius: 10,
      padding: 16, minWidth: 300, maxWidth: 340,
    }}>
      {content}
    </div>
  );
}

function LaneSummary({ clusters }) {
  const byLane = useMemo(() => {
    const m = {};
    for (const c of clusters) {
      if (!m[c.lane]) m[c.lane] = { count: 0, threads: 0, avgUnsolved: 0, promoted: 0 };
      m[c.lane].count++;
      m[c.lane].threads += c.thread_count;
      m[c.lane].avgUnsolved += c.unsolved_rate;
      if (c.promoted) m[c.lane].promoted++;
    }
    for (const k of Object.keys(m)) {
      m[k].avgUnsolved = m[k].avgUnsolved / m[k].count;
    }
    return m;
  }, [clusters]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
      {Object.entries(LANES).map(([key, lane]) => {
        const stats = byLane[key];
        if (!stats) return null;
        return (
          <div key={key} style={{
            background: "#0c0c14", border: "1px solid #1e293b",
            borderLeft: `3px solid ${lane.color}`, borderRadius: 8, padding: "10px 12px",
          }}>
            <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 4 }}>
              {lane.label}
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
              <span style={{ fontSize: 18, fontWeight: 700, color: lane.color }}>{stats.count}</span>
              <span style={{ fontSize: 10, color: "#64748b" }}>clusters</span>
            </div>
            <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 4 }}>
              {stats.threads} threads • {pct(stats.avgUnsolved)} unsolved
            </div>
            <div style={{ fontSize: 10, color: "#64748b", marginTop: 2 }}>
              ×{lane.weight} weight • {stats.promoted} promoted
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CompositeChart({ clusters, selected, onSelect }) {
  const data = useMemo(() =>
    clusters.slice(0, 15).map(c => ({
      ...c,
      shortLabel: c.label.length > 22 ? c.label.slice(0, 20) + "…" : c.label,
      fill: (LANES[c.lane] || LANES.other).color,
    })),
    [clusters]
  );

  return (
    <div style={{ background: "#0c0c14", border: "1px solid #1e293b", borderRadius: 10, padding: 16 }}>
      <div style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "1px", marginBottom: 12 }}>
        TOP 15 — COMPOSITE SCORE (LANE-WEIGHTED)
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 16 }}
          onClick={(e) => e?.activePayload && onSelect(e.activePayload[0].payload)}>
          <XAxis type="number" domain={[0, 0.8]} tick={{ fill: "#475569", fontSize: 9 }} axisLine={{ stroke: "#1e293b" }} tickLine={false} />
          <YAxis type="category" dataKey="shortLabel" width={160}
            tick={{ fill: "#94a3b8", fontSize: 9 }} axisLine={false} tickLine={false} />
          <Tooltip
            contentStyle={{ background: "#0c0c18", border: "1px solid #27273a", borderRadius: 6, fontSize: 11 }}
            labelStyle={{ color: "#e2e8f0" }}
            itemStyle={{ color: "#94a3b8" }}
            formatter={(v) => fmt(v, 4)}
          />
          <Bar dataKey="composite" radius={[0, 4, 4, 0]} cursor="pointer">
            {data.map((d, i) => (
              <Cell key={i} fill={d.fill} fillOpacity={selected?.slug === d.slug ? 1 : 0.7} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function ContentCandidates() {
  return (
    <div style={{ background: "#0c0c14", border: "1px solid #1e293b", borderRadius: 10, padding: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 12 }}>
        <BookOpen size={12} color="#ec4899" />
        <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "1px" }}>
          CONTENT CANDIDATES (LANE-AGNOSTIC)
        </span>
      </div>
      {CONTENT_CANDIDATES.map(c => (
        <div key={c.slug} style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "8px 0", borderBottom: "1px solid #1e293b",
        }}>
          <div>
            <div style={{ fontSize: 11, color: "#e2e8f0", fontWeight: 500 }}>{c.label}</div>
            <div style={{ fontSize: 10, color: "#64748b" }}>{pct(c.unsolved_rate)} unsolved</div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: "#ec4899" }}>
            <Eye size={10} /> {c.high_view_threads} hi-view
          </div>
        </div>
      ))}
    </div>
  );
}

function UncategorizedMonitor() {
  const isWarning = UNCATEGORIZED.pct > 15;
  return (
    <div style={{
      background: "#0c0c14", border: `1px solid ${isWarning ? "#f59e0b33" : "#1e293b"}`,
      borderRadius: 10, padding: 16,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <AlertTriangle size={12} color={isWarning ? "#f59e0b" : "#64748b"} />
        <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "1px" }}>
          UNCATEGORIZED MONITOR
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
        <span style={{
          fontSize: 22, fontWeight: 700, fontVariantNumeric: "tabular-nums",
          color: isWarning ? "#f59e0b" : "#94a3b8",
        }}>
          {UNCATEGORIZED.pct}%
        </span>
        <span style={{ fontSize: 10, color: "#64748b" }}>
          ({UNCATEGORIZED.count} / {UNCATEGORIZED.total} threads)
        </span>
      </div>
      <div style={{ fontSize: 10, color: "#64748b", marginTop: 4 }}>
        {UNCATEGORIZED.pct > 20
          ? "⚠ Above 20% — consider embeddings for v2"
          : UNCATEGORIZED.pct > 15
            ? "Approaching threshold — review taxonomy coverage"
            : "Within tolerance — taxonomy coverage healthy"}
      </div>
    </div>
  );
}

// ── Main Dashboard ───────────────────────────────────────────────────────

export default function CommunityClusterDashboard() {
  const isMobile = useIsMobile();
  const [selected, setSelected] = useState(null);
  const [laneFilter, setLaneFilter] = useState("all");
  const [showOnlyPromoted, setShowOnlyPromoted] = useState(false);
  const [showOnlyOutliers, setShowOnlyOutliers] = useState(false);

  const rankedClusters = useMemo(() =>
    CLUSTERS.map((c, i) => ({ ...c, rank: i + 1 })),
    []
  );

  const filtered = useMemo(() => {
    let list = rankedClusters;
    if (laneFilter !== "all") list = list.filter(c => c.lane === laneFilter);
    if (showOnlyPromoted) list = list.filter(c => c.promoted);
    if (showOnlyOutliers) list = list.filter(c => c.outlier);
    return list;
  }, [rankedClusters, laneFilter, showOnlyPromoted, showOnlyOutliers]);

  return (
    <div style={{
      background: "#0a0a0f", color: "#e2e8f0", minHeight: "100vh",
      fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
      backgroundImage: `
        linear-gradient(rgba(59,130,246,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(59,130,246,0.03) 1px, transparent 1px)
      `,
      backgroundSize: "32px 32px",
    }}>
      <div style={{ maxWidth: 1280, margin: "0 auto", padding: isMobile ? "16px 12px" : "24px 32px" }}>

        {/* Header */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <Activity size={16} color="#3b82f6" />
            <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "1px" }}>
              VIGIL COMMUNITY SCANNER
            </span>
          </div>
          <h1 style={{ fontSize: isMobile ? 20 : 24, fontWeight: 700, color: "#e2e8f0", margin: "4px 0 6px" }}>
            Cluster Intelligence Dashboard
          </h1>
          <div style={{ fontSize: 10, color: "#64748b" }}>
            Digest: {DIGEST_DATE} • Window: {WINDOW} • {rankedClusters.length} clusters scored • {CLUSTERS.reduce((s,c) => s + c.thread_count, 0)} threads
          </div>
        </div>

        {/* Lane Summary */}
        <div style={{ marginBottom: 20 }}>
          <LaneSummary clusters={rankedClusters} />
        </div>

        {/* Filters */}
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16,
          alignItems: "center",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 4, marginRight: 8 }}>
            <Filter size={12} color="#64748b" />
            <span style={{ fontSize: 9, color: "#475569", textTransform: "uppercase", letterSpacing: "1px" }}>FILTER</span>
          </div>
          {["all", ...Object.keys(LANES)].map(k => (
            <button key={k} onClick={() => setLaneFilter(k)} style={{
              background: laneFilter === k ? (k === "all" ? "rgba(59,130,246,0.12)" : LANES[k]?.bg) : "transparent",
              border: `1px solid ${laneFilter === k ? (k === "all" ? "#3b82f6" : LANES[k]?.color) + "44" : "#1e293b"}`,
              color: laneFilter === k ? (k === "all" ? "#3b82f6" : LANES[k]?.color) : "#64748b",
              borderRadius: 6, padding: "4px 10px", cursor: "pointer",
              fontSize: 10, fontWeight: 500, fontFamily: "inherit",
              transition: "all 0.15s",
            }}>
              {k === "all" ? "All" : LANES[k]?.label}
            </button>
          ))}
          <div style={{ borderLeft: "1px solid #1e293b", height: 20, margin: "0 4px" }} />
          <button onClick={() => setShowOnlyOutliers(!showOnlyOutliers)} style={{
            background: showOnlyOutliers ? "rgba(245,158,11,0.12)" : "transparent",
            border: `1px solid ${showOnlyOutliers ? "#f59e0b44" : "#1e293b"}`,
            color: showOnlyOutliers ? "#f59e0b" : "#64748b",
            borderRadius: 6, padding: "4px 10px", cursor: "pointer",
            fontSize: 10, fontWeight: 500, fontFamily: "inherit",
            display: "flex", alignItems: "center", gap: 4,
          }}>
            <Zap size={10} /> Outliers
          </button>
          <button onClick={() => setShowOnlyPromoted(!showOnlyPromoted)} style={{
            background: showOnlyPromoted ? "rgba(16,185,129,0.12)" : "transparent",
            border: `1px solid ${showOnlyPromoted ? "#10b98144" : "#1e293b"}`,
            color: showOnlyPromoted ? "#10b981" : "#64748b",
            borderRadius: 6, padding: "4px 10px", cursor: "pointer",
            fontSize: 10, fontWeight: 500, fontFamily: "inherit",
            display: "flex", alignItems: "center", gap: 4,
          }}>
            <ArrowUpRight size={10} /> Promoted
          </button>
        </div>

        {/* Main Content */}
        <div style={{
          display: isMobile ? "block" : "flex",
          gap: 20, alignItems: "flex-start",
        }}>
          {/* Cluster List */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
              {filtered.map(c => (
                <ClusterCard
                  key={c.slug}
                  cluster={c}
                  selected={selected}
                  onClick={setSelected}
                />
              ))}
              {filtered.length === 0 && (
                <div style={{
                  textAlign: "center", padding: 32, color: "#475569", fontSize: 11,
                  background: "#0c0c14", border: "1px solid #1e293b", borderRadius: 10,
                }}>
                  No clusters match filters
                </div>
              )}
            </div>

            {/* Composite Chart */}
            <CompositeChart clusters={rankedClusters} selected={selected} onSelect={setSelected} />

            {/* Bottom Row */}
            <div style={{
              display: "grid",
              gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
              gap: 12, marginTop: 16,
            }}>
              <ContentCandidates />
              <UncategorizedMonitor />
            </div>
          </div>

          {/* Detail Panel */}
          {!isMobile && selected && (
            <DetailPanel cluster={selected} onClose={() => setSelected(null)} isMobile={false} />
          )}
        </div>

        {/* Mobile Bottom Sheet */}
        {isMobile && selected && (
          <>
            <div
              onClick={() => setSelected(null)}
              style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 99 }}
            />
            <DetailPanel cluster={selected} onClose={() => setSelected(null)} isMobile={true} />
          </>
        )}

        {/* Footer */}
        <div style={{
          marginTop: 24, paddingTop: 16, borderTop: "1px solid #1e293b",
          fontSize: 9, color: "#475569", textAlign: "center", letterSpacing: "0.5px",
        }}>
          VIGIL COMMUNITY SCANNER • VECTIS LABS • {DIGEST_DATE}
        </div>
      </div>
    </div>
  );
}
