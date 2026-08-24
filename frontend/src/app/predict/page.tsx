"use client";
import { useEffect, useState, useMemo, useCallback } from "react";
import { fetchBuilderSets, fetchBuilderRoster, predictComp, fetchMetaSets } from "@/lib/api";
import { SectionHeader, StyleBadge, TierBadge, Icon, TraitIcon, Spinner, Empty } from "@/components/ui";

type Champion = { api_name: string; display_name: string; icon_url: string | null; cost: number; trait_api_names: string[] };
type Tier = { min_units: number; max_units: number; style: number };
type Trait = { api_name: string; display_name: string; icon_url: string | null; description: string; tiers: Tier[] };
type Roster = { set: string; number: number; traits: Trait[]; champions: Champion[] };

const MAX_BOARD = 10;

export default function CompBuilderPage() {
  const [sets, setSets]           = useState<string[]>([]);
  const [tftSet, setTftSet]       = useState("");
  const [roster, setRoster]       = useState<Roster | null>(null);
  const [loading, setLoading]     = useState(false);
  const [selected, setSelected]   = useState<string[]>([]);
  const [prediction, setPrediction] = useState<any>(null);
  const [predictionLoading, setPredictionLoading] = useState(false);
  const [predictionUnavailable, setPredictionUnavailable] = useState(false);
  const [liveSets, setLiveSets]   = useState<string[]>([]);

  useEffect(() => {
    fetchBuilderSets().then((res) => {
      setSets(res.data ?? []);
      setTftSet((current) => current || res.data?.[0] || "");
    }).catch(() => setSets([]));
    // เอาไว้เช็คว่า set ไหนมีข้อมูลแมตช์จริงให้โมเดลเทรน — set อื่นๆ (Comp Builder เปิดให้เลือกได้ทุก set รวมของเก่า/ที่ยังไม่ออก)
    // โมเดลไม่รู้จัก champion/trait เลยสักตัว sklearn จะไม่ error แต่จะทายมั่วเงียบๆ เลยต้องกันเองฝั่ง frontend
    fetchMetaSets().then((res) => setLiveSets(res.data ?? [])).catch(() => setLiveSets([]));
  }, []);

  useEffect(() => {
    if (!tftSet) return;
    setLoading(true);
    setSelected([]);
    fetchBuilderRoster(tftSet)
      .then(setRoster)
      .catch(() => setRoster(null))
      .finally(() => setLoading(false));
  }, [tftSet]);

  const toggleChampion = useCallback((apiName: string) => {
    setSelected((cur) => {
      if (cur.includes(apiName)) return cur.filter((c) => c !== apiName);
      if (cur.length >= MAX_BOARD) return cur;
      return [...cur, apiName];
    });
  }, []);

  const championsByCost = useMemo(() => {
    const groups: Record<number, Champion[]> = {};
    for (const c of roster?.champions ?? []) (groups[c.cost] ??= []).push(c);
    return groups;
  }, [roster]);

  const activeTraits = useMemo(() => {
    if (!roster) return [];
    const selectedChamps = roster.champions.filter((c) => selected.includes(c.api_name));
    const counts: Record<string, number> = {};
    for (const c of selectedChamps) for (const t of c.trait_api_names) counts[t] = (counts[t] ?? 0) + 1;

    return roster.traits
      .map((t) => {
        const count = counts[t.api_name] ?? 0;
        const sortedTiers = [...t.tiers].sort((a, b) => a.min_units - b.min_units);
        const tier = [...sortedTiers].reverse().find((tr) => count >= tr.min_units) ?? null;
        const next = sortedTiers.find((tr) => tr.min_units > count) ?? null;
        return { ...t, count, tier, next };
      })
      .filter((t) => t.count > 0)
      .sort((a, b) => (b.tier ? 1 : 0) - (a.tier ? 1 : 0) || b.count - a.count);
  }, [roster, selected]);

  // ยิงเข้าโมเดล XGBoost จริงที่เทรนไว้ทุกครั้งที่บอร์ดเปลี่ยน — ใช้ได้เฉพาะ set ที่มีข้อมูลแมตช์จริงให้เทรน (เช็คจาก liveSets)
  // ต้องเช็คเองฝั่งนี้ก่อนยิง เพราะ sklearn ไม่ error ตอนเจอ champion/trait ที่ไม่รู้จัก แค่ทายมั่วเงียบๆ แทน
  useEffect(() => {
    if (selected.length === 0) {
      setPrediction(null);
      setPredictionUnavailable(false);
      return;
    }
    if (!liveSets.includes(tftSet)) {
      setPrediction(null);
      setPredictionUnavailable(true);
      return;
    }
    setPredictionLoading(true);
    setPredictionUnavailable(false);
    predictComp({
      active_traits: activeTraits.filter((t) => t.tier).map((t) => `${t.api_name}|${t.tier.style}`),
      units:         selected.map((api) => `${api}|1`),
      items:         [],
      augments:      [],
    })
      .then(setPrediction)
      .catch(() => { setPrediction(null); setPredictionUnavailable(true); })
      .finally(() => setPredictionLoading(false));
  }, [selected, activeTraits, tftSet, liveSets]);

  return (
    <div>
      <SectionHeader title="Comp Builder" subtitle="Pick champions and see which synergies activate — works for any set, including ones with no stats yet" />

      <div className="flex gap-2 flex-wrap mb-5 items-center">
        <select
          className="text-sm border-0 rounded-full px-3.5 py-1.5 bg-gray-100 dark:bg-surface-raised text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-accent/50 cursor-pointer"
          value={tftSet}
          onChange={(e) => setTftSet(e.target.value)}
        >
          {sets.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {selected.length > 0 && (
          <button
            onClick={() => setSelected([])}
            className="text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100"
          >
            Clear board
          </button>
        )}
      </div>

      {loading ? <Spinner /> : !roster ? <Empty message="No roster data available" /> : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Champion picker */}
          <div className="lg:col-span-2 space-y-4">
            {/* Board */}
            <div className="bg-white dark:bg-surface-card border border-surface-border rounded-xl p-3">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400">Your board</p>
                <p className="text-xs text-gray-400 dark:text-gray-500">{selected.length}/{MAX_BOARD}</p>
              </div>
              {selected.length === 0 ? (
                <p className="text-xs text-gray-400 dark:text-gray-600 py-3 text-center">Click champions below to add them</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {selected.map((api) => {
                    const c = roster.champions.find((x) => x.api_name === api);
                    if (!c) return null;
                    return (
                      <button key={api} onClick={() => toggleChampion(api)} className="relative group">
                        <Icon src={c.icon_url} alt={c.display_name} size={40} />
                        <span className="absolute inset-0 rounded-lg bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs font-bold">✕</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Roster grouped by cost */}
            {Object.keys(championsByCost).sort((a, b) => Number(a) - Number(b)).map((cost) => (
              <div key={cost}>
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">{cost} Cost</p>
                <div className="flex flex-wrap gap-2">
                  {championsByCost[Number(cost)].map((c) => {
                    const isSelected = selected.includes(c.api_name);
                    return (
                      <button
                        key={c.api_name}
                        onClick={() => toggleChampion(c.api_name)}
                        title={c.display_name}
                        className={`rounded-lg transition-all ${isSelected ? "ring-2 ring-accent" : "opacity-70 hover:opacity-100"}`}
                      >
                        <Icon src={c.icon_url} alt={c.display_name} size={40} />
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
            {roster.champions.length === 0 && (
              <p className="text-sm text-gray-400 dark:text-gray-600 py-6 text-center">
                No champions revealed for {roster.set} yet — check back as more get datamined.
              </p>
            )}
          </div>

          <div className="space-y-4">
            {/* Model prediction */}
            {selected.length > 0 && (
              <div className="bg-white dark:bg-surface-card border border-surface-border rounded-xl p-4">
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Predicted top4 %</p>
                {predictionLoading ? (
                  <p className="text-xs text-gray-400 dark:text-gray-600">Calculating…</p>
                ) : prediction ? (
                  <div className="flex items-center gap-4">
                    <span className="text-2xl font-bold text-accent tabular-nums">{prediction.top4_probability}%</span>
                    <TierBadge tier={prediction.tier} />
                  </div>
                ) : predictionUnavailable ? (
                  <p className="text-xs text-gray-400 dark:text-gray-600">
                    No prediction available for {roster.set} — the model is only trained on sets with real match data.
                  </p>
                ) : null}
              </div>
            )}

            {/* Active traits */}
            <div className="bg-white dark:bg-surface-card border border-surface-border rounded-xl p-4 h-fit">
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3">Active traits</p>
              {activeTraits.length === 0 ? (
                <p className="text-xs text-gray-400 dark:text-gray-600">No traits active yet</p>
              ) : (
                <div className="space-y-3">
                  {activeTraits.map((t) => (
                    <div key={t.api_name} className="flex gap-2.5">
                      <TraitIcon src={t.icon_url} alt={t.display_name} style={t.tier?.style} size={28} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{t.display_name}</span>
                          <span className="text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                            {t.count}{t.next ? `/${t.next.min_units}` : ""}
                          </span>
                          {t.tier && <StyleBadge style={t.tier.style} />}
                        </div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">{t.description}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
