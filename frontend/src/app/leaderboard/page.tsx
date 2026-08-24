"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { fetchRankedLeaderboard } from "@/lib/api";
import { SectionHeader, RankNumber, Spinner, Empty } from "@/components/ui";
import { REGION_GROUPS } from "@/lib/regions";

const TIERS   = ["challenger", "grandmaster", "master", "diamond", "emerald", "platinum"];

export default function LeaderboardPage() {
  const [region, setRegion]   = useState("");
  const [tier, setTier]       = useState("");
  const [rows, setRows]       = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetchRankedLeaderboard({ region: region || undefined, tier: tier || undefined, limit: 50 })
      .then((res) => setRows(res.data ?? []))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [region, tier]);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <SectionHeader title="Leaderboard" subtitle="Top ranked players, sorted by LP" />

      <div className="flex gap-2 flex-wrap mb-5">
        <select
          className="text-sm border-0 rounded-full px-3.5 py-1.5 bg-gray-100 dark:bg-surface-raised text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent/50 cursor-pointer"
          value={region}
          onChange={(e) => setRegion(e.target.value)}
        >
          <option value="">All regions</option>
          {REGION_GROUPS.map((g) => (
            <optgroup key={g.label} label={g.label}>
              {g.regions.map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
            </optgroup>
          ))}
        </select>
        <select
          className="text-sm border-0 rounded-full px-3.5 py-1.5 bg-gray-100 dark:bg-surface-raised text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent/50 cursor-pointer"
          value={tier}
          onChange={(e) => setTier(e.target.value)}
        >
          <option value="">All tiers</option>
          {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {loading ? <Spinner /> : rows.length === 0 ? <Empty /> : (
        <div className="border border-gray-200 dark:border-surface-border rounded-xl overflow-hidden bg-white dark:bg-surface-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-surface-border text-left text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-surface-raised/50">
                <th className="px-4 py-3 font-medium">#</th>
                <th className="px-4 py-3 font-medium">Summoner</th>
                <th className="px-4 py-3 font-medium">Tier</th>
                <th className="px-4 py-3 font-medium">LP</th>
                <th className="px-4 py-3 font-medium">Top4 count</th>
                <th className="px-4 py-3 font-medium">Top4 rate</th>
                <th className="px-4 py-3 font-medium">Games</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50 dark:divide-surface-border/60">
              {rows.map((r) => (
                <tr key={r.puuid} className="hover:bg-gray-50 dark:hover:bg-surface-raised/60 transition-colors">
                  <td className="px-4 py-3"><RankNumber n={r.rank} /></td>
                  <td className="px-4 py-3">
                    <Link href={`/summoner/${r.puuid}`} className="font-medium text-gray-900 dark:text-gray-100 hover:text-accent">
                      {r.display_name ?? `${r.puuid.slice(0, 10)}…`}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-400 uppercase text-xs">{r.tier}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-gray-100 font-medium tabular-nums">{r.lp?.toLocaleString()}</td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400 tabular-nums">{r.top4_count}</td>
                  <td className="px-4 py-3 font-medium text-accent tabular-nums">{r.top4_rate}%</td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400 tabular-nums">{r.games}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
