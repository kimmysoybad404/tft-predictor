"use client";
import { useEffect, useState, useCallback } from "react";
import { fetchTierList } from "@/lib/api";
import { TierBadge, StyleBadge, Spinner, Empty, SectionHeader, TraitIcon, Icon, RankNumber, StatPill } from "@/components/ui";

const TIERS = ["S", "A", "B", "C", "D"];
const TABS  = ["traits", "comps"] as const;
type Tab = typeof TABS[number];

export default function TierListPage() {
  const [tab, setTab]         = useState<Tab>("traits");
  const [tier, setTier]       = useState("");
  const [data, setData]       = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchTierList(tab, tier || undefined);
      setData(res.data);
    } catch { setData([]); }
    finally { setLoading(false); }
  }, [tab, tier]);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <SectionHeader title="Tier List" subtitle="Trait & comp rankings from the prediction model" />

      {/* Tabs */}
      <div className="flex gap-1 mb-5 border-b border-gray-200 dark:border-surface-border">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-sm px-4 py-2 capitalize border-b-2 transition-colors ${
              tab === t
                ? "border-accent text-gray-900 dark:text-gray-100 font-semibold"
                : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="flex gap-2 flex-wrap mb-5">
        <select
          className="text-sm border-0 rounded-full px-3.5 py-1.5 bg-gray-100 dark:bg-surface-raised text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent/50 cursor-pointer"
          value={tier}
          onChange={(e) => setTier(e.target.value)}
        >
          <option value="">All tiers</option>
          {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {loading ? <Spinner /> : data.length === 0 ? <Empty /> : tab === "traits" ? (
        <div className="border border-gray-200 dark:border-surface-border rounded-xl overflow-hidden bg-white dark:bg-surface-card divide-y divide-gray-100 dark:divide-surface-border">
          {data.map((row, i) => (
            <div key={i} className="flex items-center gap-4 px-4 py-3 hover:bg-gray-50 dark:hover:bg-surface-raised/60 transition-colors">
              <TierBadge tier={row.tier} />

              <div className="flex items-center gap-2.5 flex-1 min-w-0">
                <TraitIcon src={row.icon_url} alt={row.display_name ?? row.name} style={row.style} />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{row.display_name ?? row.name}</p>
                  <StyleBadge style={row.style} />
                </div>
              </div>

              <div className="flex items-center gap-5 shrink-0">
                <StatPill label="Plays" value={row.play_count?.toLocaleString()} />
                <StatPill label="Avg place" value={row.avg_placement?.toFixed(2)} />
                <StatPill label="Top4 %" value={`${row.top4_rate}%`} emphasize />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {data.map((comp, i) => (
            <div key={i} className="bg-white dark:bg-surface-card border border-gray-200 dark:border-surface-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <RankNumber n={i + 1} />
                  <div className="flex items-center gap-2 flex-wrap">
                    {(comp.key_traits_info ?? []).map((kt: any, j: number) => (
                      <span key={j} className="flex items-center gap-1.5 text-sm text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-surface-raised rounded-lg px-2 py-1">
                        <TraitIcon src={kt.icon_url} alt={kt.display_name} style={kt.style} size={20} />
                        {kt.display_name}
                      </span>
                    ))}
                    {(!comp.key_traits_info || comp.key_traits_info.length === 0) && (
                      <span className="text-sm text-gray-900 dark:text-gray-100">{comp.comp_label}</span>
                    )}
                  </div>
                </div>
                <TierBadge tier={comp.tier} />
              </div>
              {comp.key_units_info?.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap pl-9 mb-3">
                  {comp.key_units_info.map((u: any) => (
                    <Icon key={u.character_id} src={u.icon_url} alt={u.display_name} size={32} />
                  ))}
                </div>
              )}
              <div className="flex items-center gap-6 pl-9">
                <StatPill label="Plays" value={comp.play_count?.toLocaleString()} />
                <StatPill label="Avg place" value={comp.avg_placement?.toFixed(2)} />
                <StatPill label="Top4 %" value={`${comp.top4_rate}%`} emphasize />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
