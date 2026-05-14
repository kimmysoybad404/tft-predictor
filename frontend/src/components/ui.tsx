"use client";
import clsx from "clsx";

const tierStyles: Record<string, string> = {
  S: "bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400",
  A: "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400",
  B: "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400",
  C: "bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400",
  D: "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400",
};

export function TierBadge({ tier }: { tier: string }) {
  return (
    <span className={clsx("text-xs font-medium px-2 py-0.5 rounded", tierStyles[tier] ?? "bg-gray-100 text-gray-500")}>
      {tier}
    </span>
  );
}

const styleLabels: Record<number, string> = { 1: "Bronze", 2: "Silver", 3: "Gold", 4: "Prismatic" };
const styleStyles: Record<number, string> = {
  1: "bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400",
  2: "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400",
  3: "bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400",
  4: "bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-400",
};

export function StyleBadge({ style }: { style: number }) {
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded", styleStyles[style] ?? "bg-gray-100 text-gray-500")}>
      {styleLabels[style] ?? style}
    </span>
  );
}

export function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-3">
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</p>
      <p className="text-xl font-medium text-gray-900 dark:text-gray-100">{value}</p>
    </div>
  );
}

export function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-lg font-medium text-gray-900 dark:text-gray-100">{title}</h1>
      {subtitle && <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{subtitle}</p>}
    </div>
  );
}

export function FilterBar({
  regions, tiers, selected, onChange,
}: {
  regions: string[];
  tiers: string[];
  selected: { region: string; tier: string };
  onChange: (key: "region" | "tier", val: string) => void;
}) {
  const cls = "text-sm border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-1 focus:ring-gray-300 dark:focus:ring-gray-600";
  return (
    <div className="flex gap-2 flex-wrap mb-5">
      <select className={cls} value={selected.region} onChange={(e) => onChange("region", e.target.value)}>
        <option value="">All regions</option>
        {regions.map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
      </select>
      <select className={cls} value={selected.tier} onChange={(e) => onChange("tier", e.target.value)}>
        <option value="">All tiers</option>
        {tiers.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="w-5 h-5 border-2 border-gray-200 dark:border-gray-700 border-t-gray-600 dark:border-t-gray-300 rounded-full animate-spin" />
    </div>
  );
}

export function Empty({ message = "No data found" }: { message?: string }) {
  return <div className="text-center py-16 text-sm text-gray-400 dark:text-gray-600">{message}</div>;
}