"use client";

import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

// ── Card ────────────────────────────────────────────────
interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}
export function Card({ children, className, hover }: CardProps) {
  return (
    <div className={cn("card", hover && "card-hover", className)}>
      {children}
    </div>
  );
}

// ── Card Header ─────────────────────────────────────────
interface CardHeaderProps {
  icon?: ReactNode;
  title: string;
  action?: ReactNode;
  className?: string;
}
export function CardHeader({ icon, title, action, className }: CardHeaderProps) {
  return (
    <div className={cn("flex items-center justify-between mb-4", className)}>
      <div className="flex items-center gap-2">
        {icon && <span className="text-[var(--gold)] shrink-0">{icon}</span>}
        <span className="text-sm font-semibold text-[var(--text)]">{title}</span>
      </div>
      {action}
    </div>
  );
}

// ── Page Header ─────────────────────────────────────────
interface PageHeaderProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}
export function PageHeader({ title, subtitle, action }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div>
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

// ── Stat Card ────────────────────────────────────────────
interface StatCardProps {
  label: string;
  value: string | number | undefined | null;
  sub?: string;
  color?: string;
  icon?: ReactNode;
}
export function StatCard({ label, value, sub, color, icon }: StatCardProps) {
  return (
    <Card>
      <div className="p-4">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">{label}</p>
          {icon && <span className="text-[var(--text-faint)]">{icon}</span>}
        </div>
        <p className={cn("text-2xl font-bold font-mono", color ?? "text-[var(--text)]")}>
          {value ?? "—"}
        </p>
        {sub && <p className="text-xs text-[var(--text-muted)] mt-1">{sub}</p>}
      </div>
    </Card>
  );
}

// ── Signal Badge ─────────────────────────────────────────
export function SignalBadge({ type }: { type: string }) {
  const cls =
    type === "BUY" ? "badge-buy" :
    type === "SELL" ? "badge-sell" :
    "badge-notrade";
  return <span className={cls}>{type}</span>;
}

// ── Direction Badge ──────────────────────────────────────
export function DirectionBadge({ direction }: { direction: string }) {
  const colorMap: Record<string, string> = {
    bullish: "text-[var(--green)] bg-green-500/10 border-green-500/20",
    bearish: "text-[var(--red)] bg-red-500/10 border-red-500/20",
    neutral: "text-[var(--text-muted)] bg-gray-500/10 border-gray-500/20",
  };
  return (
    <span className={cn(
      "inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border",
      colorMap[direction] ?? colorMap.neutral
    )}>
      {direction?.toUpperCase()}
    </span>
  );
}

// ── Impact Badge ─────────────────────────────────────────
export function ImpactBadge({ score }: { score: number | null | undefined }) {
  if (!score) return null;
  const cls =
    score >= 8 ? "text-[var(--red)] bg-red-500/10 border-red-500/20" :
    score >= 5 ? "text-[var(--gold)] bg-yellow-500/10 border-yellow-500/20" :
    "text-[var(--text-muted)] bg-gray-500/10 border-gray-500/20";
  return (
    <span className={cn("inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono border", cls)}>
      {score}/10
    </span>
  );
}

// ── Skeleton ─────────────────────────────────────────────
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

export function SkeletonCard() {
  return (
    <Card>
      <div className="p-4 space-y-3">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-3 w-20" />
      </div>
    </Card>
  );
}

export function SkeletonRow() {
  return (
    <div className="flex gap-4 px-3 py-3">
      <Skeleton className="h-4 w-16" />
      <Skeleton className="h-4 w-24 flex-1" />
      <Skeleton className="h-4 w-20" />
    </div>
  );
}

// ── Empty State ──────────────────────────────────────────
interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}
export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-14 px-4 text-center">
      {icon && <div className="text-[var(--text-faint)] mb-3 opacity-40">{icon}</div>}
      <p className="text-sm font-medium text-[var(--text-muted)]">{title}</p>
      {description && <div className="text-xs text-[var(--text-faint)] mt-1 max-w-xs">{description}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ── Score Bar ────────────────────────────────────────────
interface ScoreBarProps {
  score: number;
  direction?: string;
  className?: string;
}
export function ScoreBar({ score, direction, className }: ScoreBarProps) {
  const color =
    direction === "bullish" ? "bg-green-500" :
    direction === "bearish" ? "bg-red-500" :
    "bg-[var(--text-muted)]";
  return (
    <div className={cn("score-bar-track", className)}>
      <div className={cn("score-bar-fill", color)} style={{ width: `${Math.min(Math.max(score, 0), 100)}%` }} />
    </div>
  );
}

// ── Select ───────────────────────────────────────────────
interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: { value: string; label: string }[];
}
export function Select({ options, className, ...props }: SelectProps) {
  return (
    <select
      className={cn(
        "input text-sm py-1.5 pr-8 appearance-none cursor-pointer",
        className
      )}
      {...props}
    >
      {options.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}
