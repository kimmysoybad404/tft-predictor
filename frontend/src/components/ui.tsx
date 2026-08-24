"use client";
import clsx from "clsx";

const tierStyles: Record<string, string> = {
  S: "bg-tier-S/15 text-tier-S ring-1 ring-inset ring-tier-S/40",
  A: "bg-tier-A/15 text-tier-A ring-1 ring-inset ring-tier-A/40",
  B: "bg-tier-B/15 text-tier-B ring-1 ring-inset ring-tier-B/40",
  C: "bg-tier-C/15 text-tier-C ring-1 ring-inset ring-tier-C/40",
  D: "bg-tier-D/15 text-tier-D ring-1 ring-inset ring-tier-D/40",
};

export function TierBadge({ tier }: { tier: string }) {
  return (
    <span className={clsx("inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold", tierStyles[tier] ?? "bg-gray-100 text-gray-500")}>
      {tier}
    </span>
  );
}

const styleLabels: Record<number, string> = { 1: "Bronze", 2: "Silver", 3: "Gold", 4: "Prismatic" };
const styleStyles: Record<number, string> = {
  1: "bg-amber-800/20 text-amber-600 dark:text-amber-500",
  2: "bg-gray-400/20 text-gray-500 dark:text-gray-300",
  3: "bg-gold/20 text-gold-muted dark:text-gold",
  4: "bg-fuchsia-500/15 text-fuchsia-500 dark:text-fuchsia-400",
};

export function StyleBadge({ style }: { style: number }) {
  return (
    <span className={clsx("text-[11px] font-medium px-2 py-0.5 rounded", styleStyles[style] ?? "bg-gray-100 text-gray-500")}>
      {styleLabels[style] ?? style}
    </span>
  );
}

export function StatPill({ label, value, emphasize = false, compact = false }: { label: string; value: string | number; emphasize?: boolean; compact?: boolean }) {
  return (
    <div className={clsx("flex flex-col items-center", !compact && "min-w-[64px]")}>
      <span className="text-[11px] text-gray-500 dark:text-gray-400 mb-0.5 text-center leading-tight">{label}</span>
      <span className={clsx("text-sm font-semibold tabular-nums", emphasize ? "text-accent" : "text-gray-900 dark:text-gray-100")}>
        {value}
      </span>
    </div>
  );
}

export function RankNumber({ n }: { n: number }) {
  const top3 = n <= 3;
  return (
    <span
      className={clsx(
        "inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold shrink-0 tabular-nums",
        top3 ? "bg-gold/20 text-gold-muted dark:text-gold" : "text-gray-400 dark:text-gray-600"
      )}
    >
      {n}
    </span>
  );
}

export function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-gray-100 dark:bg-surface-raised rounded-lg p-3">
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</p>
      <p className="text-xl font-semibold text-gray-900 dark:text-gray-100">{value}</p>
    </div>
  );
}

export function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-lg font-bold text-gray-900 dark:text-gray-100">{title}</h1>
      {subtitle && <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{subtitle}</p>}
    </div>
  );
}

export function FilterBar({
  regionGroups, tiers, sets, selected, onChange,
}: {
  regionGroups: { label: string; regions: string[] }[];
  tiers: string[];
  sets?: string[];
  selected: { region: string; tier: string; set?: string };
  onChange: (key: "region" | "tier" | "set", val: string) => void;
}) {
  const cls = "text-sm border-0 rounded-full px-3.5 py-1.5 bg-gray-100 dark:bg-surface-raised text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent/50 cursor-pointer";
  return (
    <div className="flex gap-2 flex-wrap mb-5">
      {sets && (
        <select className={cls} value={selected.set ?? ""} onChange={(e) => onChange("set", e.target.value)}>
          <option value="">All sets</option>
          {sets.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      )}
      <select className={cls} value={selected.region} onChange={(e) => onChange("region", e.target.value)}>
        <option value="">All regions</option>
        {regionGroups.map((g) => (
          <optgroup key={g.label} label={g.label}>
            {g.regions.map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
          </optgroup>
        ))}
      </select>
      <select className={cls} value={selected.tier} onChange={(e) => onChange("tier", e.target.value)}>
        <option value="">All tiers</option>
        {tiers.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
    </div>
  );
}

export function Icon({ src, alt, size = 28 }: { src?: string | null; alt: string; size?: number }) {
  if (!src) return <div style={{ width: size, height: size }} className="rounded-lg bg-gray-100 dark:bg-surface-raised shrink-0" />;
  return (
    <img
      src={src}
      alt={alt}
      width={size}
      height={size}
      className="rounded-lg shrink-0 object-contain bg-gray-100 dark:bg-surface-raised ring-1 ring-black/5 dark:ring-white/10"
      onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = "hidden"; }}
    />
  );
}

// Trait icons จาก Community Dragon เป็นแค่ silhouette ขาว/เทาเล็กๆ (32x32) ที่เกมจริงเอาไปทาสีตาม tier เอง
// ไม่ใช่ full-color art แบบ champion/item — ต้องใส่พื้นหลังวงกลมสีตาม tier เองถึงจะดูสมบูรณ์ ไม่ดูเหมือนภาพเสีย
const traitTierBg: Record<number, string> = {
  1: "bg-amber-800",
  2: "bg-gray-400",
  3: "bg-amber-400",
  4: "bg-fuchsia-500",
  5: "bg-accent",
  6: "bg-purple-600",
};

export function TraitIcon({ src, alt, style, size = 32 }: { src?: string | null; alt: string; style?: number | null; size?: number }) {
  const bg = style ? (traitTierBg[style] ?? "bg-gray-500") : "bg-gray-300 dark:bg-surface-raised";
  return (
    <div
      style={{ width: size, height: size }}
      className={clsx("rounded-full shrink-0 flex items-center justify-center ring-1 ring-black/10 dark:ring-white/10", bg)}
    >
      {src && (
        <img
          src={src}
          alt={alt}
          style={{ width: size * 0.62, height: size * 0.62 }}
          className="object-contain"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = "hidden"; }}
        />
      )}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="w-5 h-5 border-2 border-gray-200 dark:border-surface-raised border-t-accent rounded-full animate-spin" />
    </div>
  );
}

export function Empty({ message = "No data found" }: { message?: string }) {
  return <div className="text-center py-16 text-sm text-gray-400 dark:text-gray-600">{message}</div>;
}
