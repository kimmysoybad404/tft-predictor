"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { fetchSummonerProfile } from "@/lib/api";
import { TraitIcon, Icon, StatPill, Spinner, Empty } from "@/components/ui";

function placementColor(p: number): string {
  if (p === 1) return "text-gold-muted dark:text-gold";
  if (p <= 4) return "text-accent";
  return "text-gray-400 dark:text-gray-500";
}

function timeAgo(iso: string | null): string {
  if (!iso) return "-";
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function formatLength(seconds?: number): string {
  if (!seconds) return "-";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}m ${s}s`;
}

function UnitCard({ u }: { u: any }) {
  return (
    <div className="flex flex-col items-center gap-1 w-11">
      <div className="relative">
        <Icon src={u.icon_url} alt={u.display_name} size={36} />
        <span className="absolute -top-1.5 left-1/2 -translate-x-1/2 text-[9px] font-bold text-gold whitespace-nowrap leading-none">
          {"★".repeat(u.star || 1)}
        </span>
      </div>
      <div className="flex gap-0.5 h-3.5">
        {u.items.slice(0, 3).map((it: any, i: number) => (
          <Icon key={i} src={it.icon_url} alt={it.display_name} size={14} />
        ))}
      </div>
    </div>
  );
}

export default function SummonerProfilePage() {
  const params = useParams<{ puuid: string }>();
  const router = useRouter();
  const [profile, setProfile] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    fetchSummonerProfile(params.puuid)
      .then(setProfile)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [params.puuid]);

  return (
    <div>
      <button
        onClick={() => router.back()}
        className="text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 mb-4"
      >
        ← Back
      </button>

      {loading ? <Spinner /> : error || !profile ? <Empty message="No match history found for this player" /> : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Sidebar */}
          <div className="space-y-4">
            <div className="bg-white dark:bg-surface-card border border-gray-200 dark:border-surface-border rounded-xl p-4">
              <h1 className="text-base font-bold text-gray-900 dark:text-gray-100 truncate">
                {profile.display_name ?? `${profile.puuid.slice(0, 14)}…`}
              </h1>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 uppercase mb-3">{profile.region}</p>

              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-semibold uppercase text-gold-muted dark:text-gold">{profile.tier}</span>
                {profile.lp != null && <span className="text-sm font-medium text-gray-700 dark:text-gray-300 tabular-nums">{profile.lp.toLocaleString()} LP</span>}
              </div>

              <div className="grid grid-cols-4 gap-1 mb-4">
                <StatPill compact label="Games" value={profile.stats.games} />
                <StatPill compact label="Avg place" value={profile.stats.avg_placement.toFixed(2)} />
                <StatPill compact label="Top4 %" value={`${profile.stats.top4_rate}%`} emphasize />
                <StatPill compact label="Win %" value={`${profile.stats.win_rate}%`} />
              </div>

              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">Placement distribution</p>
              <div className="grid grid-cols-4 gap-1.5">
                {Object.entries(profile.stats.placement_distribution).map(([place, count]: any) => (
                  <div
                    key={place}
                    className={`rounded-md px-2 py-1.5 text-center ${place === "1" ? "bg-gold/20" : "bg-gray-50 dark:bg-surface-raised"}`}
                  >
                    <p className={`text-[10px] ${place === "1" ? "text-gold-muted dark:text-gold" : "text-gray-400 dark:text-gray-500"}`}>#{place}</p>
                    <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 tabular-nums">{count}</p>
                  </div>
                ))}
              </div>
            </div>

            {profile.top_synergies.length > 0 && (
              <div className="bg-white dark:bg-surface-card border border-gray-200 dark:border-surface-border rounded-xl p-4">
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Most synergies</p>
                <div className="space-y-2.5">
                  {profile.top_synergies.map((s: any) => (
                    <div key={s.name} className="flex items-center gap-2.5">
                      <TraitIcon src={s.icon_url} alt={s.display_name} size={26} />
                      <span className="text-sm text-gray-900 dark:text-gray-100 flex-1 truncate">{s.display_name}</span>
                      <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">{s.matches} games</span>
                      <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums w-8 text-right">#{s.avg_placement.toFixed(1)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Match history */}
          <div className="lg:col-span-2 space-y-3">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Match history</h2>
            {profile.matches.map((m: any) => (
              <div key={m.match_id} className="bg-white dark:bg-surface-card border border-gray-200 dark:border-surface-border rounded-xl p-4">
                <div className="flex items-center gap-3 mb-2">
                  <span className={`text-lg font-bold tabular-nums ${placementColor(m.placement)}`}>#{m.placement}</span>
                  <span className="text-xs text-gray-400 dark:text-gray-600">{m.tft_set}</span>
                  <span className="text-xs text-gray-400 dark:text-gray-600 ml-auto">{timeAgo(m.game_datetime)}</span>
                </div>
                <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400 mb-3">
                  <span>Round {m.last_round}</span>
                  <span>{formatLength(m.game_length)}</span>
                </div>
                <div className="flex items-center gap-1.5 mb-3 flex-wrap">
                  {m.top_traits.map((t: any) => (
                    <TraitIcon key={t.name} src={t.icon_url} alt={t.display_name} style={t.style} size={22} />
                  ))}
                </div>
                <div className="flex gap-1.5 flex-wrap">
                  {m.units.map((u: any, i: number) => <UnitCard key={i} u={u} />)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
