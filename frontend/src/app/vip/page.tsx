"use client";
import { useEffect, useState } from "react";
import { fetchVipSummoners, fetchVipDetail } from "@/lib/api";
import { StatCard, TierBadge, Spinner, Empty, SectionHeader } from "@/components/ui";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export default function VipPage() {
  const [summoners, setSummoners] = useState<any[]>([]);
  const [selected,  setSelected]  = useState<string>("");
  const [detail,    setDetail]    = useState<any>(null);
  const [loadingList,   setLoadingList]   = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    setLoadingList(true);
    fetchVipSummoners()
      .then((r) => {
        setSummoners(r.data ?? []);
        if (r.data?.length > 0) setSelected(r.data[0].puuid);
      })
      .catch(() => setSummoners([]))
      .finally(() => setLoadingList(false));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoadingDetail(true);
    setDetail(null);
    fetchVipDetail(selected)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoadingDetail(false));
  }, [selected]);

  return (
    <div>
      <SectionHeader title="VIP Players" subtitle="Tracked summoners — detailed performance breakdown" />

      {loadingList ? <Spinner /> : summoners.length === 0 ? <Empty message="No VIP players configured" /> : (
        <>
          {/* Player picker */}
          <div className="flex gap-2 flex-wrap mb-6">
            {summoners.map((s) => (
              <button
                key={s.puuid}
                onClick={() => setSelected(s.puuid)}
                className={`text-sm px-4 py-2 rounded-lg border transition-colors ${
                  selected === s.puuid
                    ? "bg-gray-900 text-white border-gray-900"
                    : "bg-white text-gray-600 border-gray-200 hover:border-gray-300"
                }`}
              >
                {s.summoner_name ?? s.puuid.slice(0, 8)}
              </button>
            ))}
          </div>

          {loadingDetail ? <Spinner /> : !detail ? <Empty message="No data for this player" /> : (
            <div className="space-y-5">
              {/* Stats */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard label="Avg placement"  value={detail.avg_placement?.toFixed(2) ?? "-"} />
                <StatCard label="Top4 rate"      value={`${detail.top4_rate?.toFixed(1) ?? "-"}%`} />
                <StatCard label="Win rate"       value={`${detail.win_rate?.toFixed(1) ?? "-"}%`} />
                <StatCard label="Matches tracked" value={detail.match_count ?? "-"} />
              </div>

              {/* Performance over time */}
              {detail.performance_history?.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-xl p-5">
                  <h3 className="text-sm font-medium text-gray-900 mb-4">Placement over time</h3>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={detail.performance_history}>
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                      <YAxis reversed domain={[1, 8]} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                      <Tooltip
                        contentStyle={{ fontSize: 12, border: "0.5px solid #e5e7eb", borderRadius: 8 }}
                        formatter={(v: any) => [`Place ${v}`, ""]}
                      />
                      <Line
                        type="monotone"
                        dataKey="placement"
                        stroke="#111827"
                        strokeWidth={1.5}
                        dot={{ r: 3, fill: "#111827" }}
                        activeDot={{ r: 4 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Most played comps */}
              {detail.top_comps?.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-100">
                    <h3 className="text-sm font-medium text-gray-900">Most played comps</h3>
                  </div>
                  {detail.top_comps.map((c: any, i: number) => (
                    <div key={i} className="flex items-center justify-between px-4 py-3 border-b border-gray-50 last:border-0">
                      <div>
                        <p className="text-sm text-gray-900">{c.comp_label}</p>
                        <p className="text-xs text-gray-400 mt-0.5">{c.play_count} games</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-sm text-gray-500">{c.avg_placement?.toFixed(2)} avg</span>
                        <span className="text-sm text-gray-500">{c.top4_rate?.toFixed(1)}% top4</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Recent matches */}
              {detail.recent_matches?.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-100">
                    <h3 className="text-sm font-medium text-gray-900">Recent matches</h3>
                  </div>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-50 text-left text-xs text-gray-400">
                        <th className="px-4 py-2 font-medium">Date</th>
                        <th className="px-4 py-2 font-medium">Placement</th>
                        <th className="px-4 py-2 font-medium">Key traits</th>
                        <th className="px-4 py-2 font-medium">Augments</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.recent_matches.map((m: any, i: number) => (
                        <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-gray-50">
                          <td className="px-4 py-3 text-gray-500">{m.date}</td>
                          <td className="px-4 py-3">
                            <span className={`font-medium ${m.placement <= 4 ? "text-green-600" : "text-red-500"}`}>
                              #{m.placement}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-gray-600 text-xs">{m.key_traits?.join(", ") ?? "-"}</td>
                          <td className="px-4 py-3 text-gray-600 text-xs">{m.augments?.slice(0, 2).join(", ") ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}