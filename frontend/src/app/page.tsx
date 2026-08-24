"use client";
import { useEffect, useState, useCallback, useMemo } from "react";
import { fetchMeta, fetchMetaSets, fetchUpcomingSet, fetchMetaTrends } from "@/lib/api";
import { StyleBadge, FilterBar, Spinner, Empty, SectionHeader, Icon, TraitIcon, RankNumber, StatPill } from "@/components/ui";
import { REGION_GROUPS } from "@/lib/regions";

const TIERS   = ["challenger", "grandmaster", "master", "diamond", "emerald", "platinum"];
const TABS    = ["traits", "augments", "units", "items"] as const;
type Tab = typeof TABS[number];

function latestSet(sets: string[]): string {
  const numbered = sets
    .map((s) => ({ s, n: parseInt(s.replace(/^TFTSet/, ""), 10) }))
    .filter((x) => !isNaN(x.n));
  if (numbered.length === 0) return "";
  return numbered.sort((a, b) => b.n - a.n)[0].s;
}

export default function MetaPage() {
  const [tab, setTab]         = useState<Tab>("traits");
  const [region, setRegion]   = useState("");
  const [tier, setTier]       = useState("");
  const [tftSet, setTftSet]   = useState("");
  const [sets, setSets]       = useState<string[]>([]);
  const [data, setData]       = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [upcoming, setUpcoming]         = useState<any>(null);
  const [showAllUpcoming, setShowAllUpcoming] = useState(false);
  const [trends, setTrends]   = useState<any>(null);

  useEffect(() => {
    fetchMetaSets()
      .then((res) => {
        setSets(res.data ?? []);
        // ค่าเริ่มต้นเป็น set ล่าสุดเสมอ กันข้อมูล set เก่าที่ยังไม่หมดอายุ (TTL) มาปนกับ meta ปัจจุบัน
        setTftSet((current) => current || latestSet(res.data ?? []));
      })
      .catch(() => setSets([]));
    fetchUpcomingSet().then((res) => setUpcoming(res.data)).catch(() => setUpcoming(null));
  }, []);

  useEffect(() => {
    if (!tftSet) return;
    fetchMetaTrends({ tft_set: tftSet }).then(setTrends).catch(() => setTrends(null));
  }, [tftSet]);

  // ใส่ trend เข้าไปในตารางหลักโดยตรง (แทนการ์ดแยก) — join ด้วย name+style
  const trendMap = useMemo(() => {
    const map: Record<string, any> = {};
    for (const t of trends?.all ?? []) map[`${t.name}|${t.style}`] = t;
    return map;
  }, [trends]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchMeta(tab, { region: region || undefined, tier: tier || undefined, tft_set: tftSet || undefined, top_n: 30 });
      setData(res.data);
    } catch { setData([]); }
    finally { setLoading(false); }
  }, [tab, region, tier, tftSet]);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <SectionHeader title="Meta Analysis" subtitle="Top performers from high-ranked players" />

      {/* Upcoming set preview — ยังไม่มีสถิติจริง เพราะยังไม่มีใครเล่น เลยโชว์ preview จาก datamine แทน */}
      {upcoming && (
        <div className="mb-6 bg-white dark:bg-surface-card border border-surface-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-accent/20 text-accent">COMING SOON</span>
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {upcoming.set} preview — no stats yet, here's what's new
            </h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {(showAllUpcoming ? upcoming.traits : upcoming.traits.slice(0, 6)).map((t: any) => (
              <div key={t.api_name} className="flex gap-3 p-3 rounded-lg bg-gray-50 dark:bg-surface-raised">
                <TraitIcon src={t.icon_url} alt={t.display_name} size={32} />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{t.display_name}</p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">{t.description}</p>
                </div>
              </div>
            ))}
          </div>
          {upcoming.traits.length > 6 && (
            <button
              onClick={() => setShowAllUpcoming((v) => !v)}
              className="text-xs font-medium text-accent hover:text-accent-muted mt-3"
            >
              {showAllUpcoming ? "Show less" : `Show all ${upcoming.traits.length} traits`}
            </button>
          )}
        </div>
      )}

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

      <FilterBar
        regionGroups={REGION_GROUPS}
        tiers={TIERS}
        sets={sets}
        selected={{ region, tier, set: tftSet }}
        onChange={(k, v) => k === "region" ? setRegion(v) : k === "tier" ? setTier(v) : setTftSet(v)}
      />

      {loading ? <Spinner /> : data.length === 0 ? <Empty /> : (
        <div className="border border-gray-200 dark:border-surface-border rounded-xl overflow-hidden bg-white dark:bg-surface-card divide-y divide-gray-100 dark:divide-surface-border">
          {data.map((row, i) => {
            const trend = tab === "traits" ? trendMap[`${row.name}|${row.style}`] : null;
            return (
              <div key={i} className="flex items-center gap-4 px-4 py-3 hover:bg-gray-50 dark:hover:bg-surface-raised/60 transition-colors">
                <RankNumber n={i + 1} />

                <div className="flex items-center gap-2.5 flex-1 min-w-0">
                  {tab === "traits" ? (
                    <TraitIcon src={row.icon_url} alt={row.display_name ?? row.name} style={row.style} />
                  ) : (
                    <Icon src={row.icon_url} alt={row.display_name ?? row.augment ?? row.character_id ?? row.item} />
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                      {row.display_name ?? row.name ?? row.augment ?? row.character_id ?? row.item}
                    </p>
                    {tab === "traits" && <StyleBadge style={row.style} />}
                  </div>
                </div>

                <div className="flex items-center gap-5 shrink-0">
                  {tab === "units" && <StatPill label="Avg star" value={`${row.avg_star?.toFixed(1)} ★`} />}
                  <StatPill label="Plays" value={row.play_count?.toLocaleString()} />
                  <StatPill label="Avg place" value={row.avg_placement?.toFixed(2)} />
                  <StatPill label="Top4 %" value={`${row.top4_rate}%`} emphasize />
                  <StatPill label="Win %" value={`${row.win_rate}%`} />
                  {tab === "traits" && (
                    <div className="flex flex-col items-center min-w-[64px]">
                      <span className="text-[11px] text-gray-500 dark:text-gray-400 mb-0.5">3d trend</span>
                      <span className={`text-sm font-semibold tabular-nums ${trend ? (trend.delta > 0 ? "text-accent" : "text-red-500") : "text-gray-400 dark:text-gray-600"}`}>
                        {trend ? `${trend.delta > 0 ? "▲" : "▼"} ${Math.abs(trend.delta)}pp` : "–"}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}