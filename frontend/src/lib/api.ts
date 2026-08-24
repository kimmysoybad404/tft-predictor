const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchMeta(
  type: "traits" | "augments" | "units" | "items",
  params: { region?: string; tier?: string; tft_set?: string; top_n?: number } = {}
) {
  const query = new URLSearchParams();
  if (params.region)  query.set("region", params.region);
  if (params.tier)    query.set("tier", params.tier);
  if (params.tft_set) query.set("tft_set", params.tft_set);
  if (params.top_n)   query.set("top_n", String(params.top_n));
  const res = await fetch(`${API}/meta/${type}?${query}`);
  if (!res.ok) throw new Error(`Failed to fetch /meta/${type}`);
  return res.json();
}

export async function fetchMetaSets() {
  const res = await fetch(`${API}/meta/sets`);
  if (!res.ok) throw new Error("Failed to fetch /meta/sets");
  return res.json();
}

export async function fetchMetaTrends(params: { tft_set?: string } = {}) {
  const query = new URLSearchParams();
  if (params.tft_set) query.set("tft_set", params.tft_set);
  const res = await fetch(`${API}/meta/trends?${query}`);
  if (!res.ok) throw new Error("Failed to fetch /meta/trends");
  return res.json();
}

export async function fetchUpcomingSet() {
  const res = await fetch(`${API}/meta/upcoming-set`);
  if (!res.ok) throw new Error("Failed to fetch /meta/upcoming-set");
  return res.json();
}

export async function fetchBuilderSets() {
  const res = await fetch(`${API}/builder/sets`);
  if (!res.ok) throw new Error("Failed to fetch /builder/sets");
  return res.json();
}

export async function fetchBuilderRoster(tftSet?: string) {
  const query = tftSet ? `?tft_set=${encodeURIComponent(tftSet)}` : "";
  const res = await fetch(`${API}/builder/roster${query}`);
  if (!res.ok) throw new Error("Failed to fetch /builder/roster");
  return res.json();
}

export async function fetchTierList(type: "traits" | "comps", tier?: string) {
  const query = new URLSearchParams();
  if (tier) query.set("tier", tier);
  const res = await fetch(`${API}/tier-list/${type}?${query}`);
  if (!res.ok) throw new Error(`Failed to fetch /tier-list/${type}`);
  return res.json();
}

export async function predictComp(payload: {
  active_traits: string[];
  units: string[];
  items: string[];
  augments: string[];
}) {
  const res = await fetch(`${API}/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Prediction failed");
  return res.json();
}

export async function fetchRankedLeaderboard(params: { region?: string; tier?: string; limit?: number } = {}) {
  const query = new URLSearchParams();
  if (params.region) query.set("region", params.region);
  if (params.tier)   query.set("tier", params.tier);
  if (params.limit)  query.set("limit", String(params.limit));
  const res = await fetch(`${API}/leaderboard/ranked?${query}`);
  if (!res.ok) throw new Error("Failed to fetch /leaderboard/ranked");
  return res.json();
}

export async function fetchSummonerProfile(puuid: string) {
  const res = await fetch(`${API}/summoner/${encodeURIComponent(puuid)}`);
  if (!res.ok) throw new Error("Failed to fetch summoner profile");
  return res.json();
}

export async function fetchAdminStatus() {
  const res = await fetch(`${API}/admin/status`);
  if (!res.ok) throw new Error("Failed to fetch /admin/status");
  return res.json();
}
