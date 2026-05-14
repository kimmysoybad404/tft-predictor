"use client";
import { useEffect, useState, useCallback } from "react";
import { fetchMeta } from "@/lib/api";
import { TierBadge, StyleBadge, FilterBar, Spinner, Empty, SectionHeader } from "@/components/ui";

const REGIONS = ["kr", "na1", "euw1", "sg2", "br1"];
const TIERS   = ["challenger", "grandmaster", "master", "diamond", "emerald", "platinum"];
const TABS    = ["traits", "augments", "units", "items"] as const;
type Tab = typeof TABS[number];

export default function MetaPage() {
  const [tab, setTab]         = useState<Tab>("traits");
  const [region, setRegion]   = useState("");
  const [tier, setTier]       = useState("");
  const [data, setData]       = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchMeta(tab, { region: region || undefined, tier: tier || undefined, top_n: 30 });
      setData(res.data);
    } catch { setData([]); }
    finally { setLoading(false); }
  }, [tab, region, tier]);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <SectionHeader title="Meta Analysis" subtitle="Top performers from high-ranked players" />

      {/* Tabs */}
      <div className="flex gap-1 mb-5 border-b border-gray-200 dark:border-gray-800">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-sm px-4 py-2 capitalize border-b-2 transition-colors ${
              tab === t
                ? "border-gray-900 dark:border-gray-100 text-gray-900 dark:text-gray-100 font-medium"
                : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <FilterBar
        regions={REGIONS}
        tiers={TIERS}
        selected={{ region, tier }}
        onChange={(k, v) => k === "region" ? setRegion(v) : setTier(v)}
      />

      {loading ? <Spinner /> : data.length === 0 ? <Empty /> : (
        <div className="border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden bg-white dark:bg-gray-900">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-800 text-left text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50">
                <th className="px-4 py-3 font-medium">#</th>
                {tab === "traits" && <th className="px-4 py-3 font-medium">Style</th>}
                <th className="px-4 py-3 font-medium capitalize">{tab.slice(0, -1)}</th>
                {tab === "units"  && <th className="px-4 py-3 font-medium">Avg star</th>}
                <th className="px-4 py-3 font-medium">Plays</th>
                <th className="px-4 py-3 font-medium">Avg place</th>
                <th className="px-4 py-3 font-medium">Top4 %</th>
                <th className="px-4 py-3 font-medium">Win %</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr
                  key={i}
                  className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                >
                  <td className="px-4 py-3 text-gray-400 dark:text-gray-600">{i + 1}</td>
                  {tab === "traits" && (
                    <td className="px-4 py-3"><StyleBadge style={row.style} /></td>
                  )}
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">
                    {row.name ?? row.augment ?? row.character_id ?? row.item}
                  </td>
                  {tab === "units" && (
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{row.avg_star?.toFixed(1)} ★</td>
                  )}
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{row.play_count?.toLocaleString()}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{row.avg_placement?.toFixed(2)}</td>
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{row.top4_rate}%</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{row.win_rate}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}