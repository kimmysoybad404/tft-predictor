"use client";
import { useState } from "react";
import { predictComp } from "@/lib/api";
import { TierBadge, StyleBadge, Spinner, SectionHeader } from "@/components/ui";

function parseLines(text: string): string[] {
  return text.split("\n").map((s) => s.trim()).filter(Boolean);
}

export default function PredictPage() {
  const [traits,   setTraits]   = useState("");
  const [units,    setUnits]    = useState("");
  const [items,    setItems]    = useState("");
  const [augments, setAugments] = useState("");
  const [result,   setResult]   = useState<any>(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  async function handleSubmit() {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await predictComp({
        active_traits: parseLines(traits),
        units:         parseLines(units),
        items:         parseLines(items),
        augments:      parseLines(augments),
      });
      setResult(res);
    } catch (e: any) {
      setError(e.message ?? "Prediction failed");
    } finally {
      setLoading(false);
    }
  }

  const styleMap: Record<string, string> = { Bronze: "1", Silver: "2", Gold: "3", Prismatic: "4" };

  return (
    <div className="max-w-2xl">
      <SectionHeader
        title="Comp Predictor"
        subtitle="Enter your comp to get top4 probability and tier"
      />

      <div className="space-y-4 mb-6">
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5 block">
            Active traits <span className="text-gray-400 dark:text-gray-500 font-normal">(one per line, format: TraitName|style e.g. Rebel|3)</span>
          </label>
          <textarea
            rows={4}
            className="w-full text-sm border border-gray-200 dark:border-gray-800 rounded-lg px-3 py-2 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-gray-300 dark:focus:ring-gray-700 font-mono"
            placeholder={"Rebel|3\nInvoker|2\nSlayer|2"}
            value={traits}
            onChange={(e) => setTraits(e.target.value)}
          />
        </div>

        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5 block">
            Units <span className="text-gray-400 dark:text-gray-500 font-normal">(format: character_id|star e.g. TFT13_Jinx|2)</span>
          </label>
          <textarea
            rows={4}
            className="w-full text-sm border border-gray-200 dark:border-gray-800 rounded-lg px-3 py-2 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-gray-300 dark:focus:ring-gray-700 font-mono"
            placeholder={"TFT13_Jinx|2\nTFT13_Ekko|1"}
            value={units}
            onChange={(e) => setUnits(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5 block">Items</label>
            <textarea
              rows={3}
              className="w-full text-sm border border-gray-200 dark:border-gray-800 rounded-lg px-3 py-2 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-gray-300 dark:focus:ring-gray-700 font-mono"
              placeholder={"TFT_Item_RabadonsDeathcap"}
              value={items}
              onChange={(e) => setItems(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1.5 block">Augments</label>
            <textarea
              rows={3}
              className="w-full text-sm border border-gray-200 dark:border-gray-800 rounded-lg px-3 py-2 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-gray-300 dark:focus:ring-gray-700 font-mono"
              placeholder={"TFT_Augment_RebelHeart"}
              value={augments}
              onChange={(e) => setAugments(e.target.value)}
            />
          </div>
        </div>
      </div>

      <button
        onClick={handleSubmit}
        disabled={loading || !traits.trim()}
        className="w-full py-2.5 text-sm font-medium bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 rounded-lg hover:bg-gray-800 dark:hover:bg-gray-200 disabled:opacity-40 transition-colors"
      >
        {loading ? "Analyzing..." : "Analyze comp"}
      </button>

      {error && (
        <p className="mt-4 text-sm text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg px-4 py-3">{error}</p>
      )}

      {result && (
        <div className="mt-6 space-y-4">
          {/* Summary */}
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">Result</h3>
              <TierBadge tier={result.tier} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Top4 probability</p>
                <p className="text-2xl font-medium text-gray-900 dark:text-gray-100">{result.top4_probability}%</p>
              </div>
              <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-3">
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Tier</p>
                <p className="text-2xl font-medium text-gray-900 dark:text-gray-100">{result.tier}</p>
              </div>
            </div>
          </div>

          {/* Trait analysis */}
          {result.trait_analysis?.length > 0 && (
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">Trait breakdown</h3>
              </div>
              {result.trait_analysis.map((t: any, i: number) => (
                <div key={i} className="flex items-center justify-between px-4 py-3 border-b border-gray-50 dark:border-gray-800/50 last:border-0">
                  <div className="flex items-center gap-2">
                    <StyleBadge style={parseInt(styleMap[t.style] ?? "1")} />
                    <span className="text-sm text-gray-900 dark:text-gray-100">{t.trait}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-gray-500 dark:text-gray-400">{t.top4_rate}% top4</span>
                    <TierBadge tier={t.tier} />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Similar comp */}
          {result.similar_comp && (
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
              <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">Similar comp in tier list</h3>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-900 dark:text-gray-100">{result.similar_comp.comp_label}</p>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{result.similar_comp.similarity}% match</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-500 dark:text-gray-400">{result.similar_comp.top4_rate}% top4</span>
                  <TierBadge tier={result.similar_comp.tier} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}