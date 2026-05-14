const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchMeta(
  type: "traits" | "augments" | "units" | "items",
  params: { region?: string; tier?: string; top_n?: number } = {}
) {
  const query = new URLSearchParams();
  if (params.region) query.set("region", params.region);
  if (params.tier)   query.set("tier", params.tier);
  if (params.top_n)  query.set("top_n", String(params.top_n));
  const res = await fetch(`${API}/meta/${type}?${query}`);
  if (!res.ok) throw new Error(`Failed to fetch /meta/${type}`);
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

export async function fetchVipSummoners() {
  const res = await fetch(`${API}/vip/summoners`);
  if (!res.ok) throw new Error("Failed to fetch VIP summoners");
  return res.json();
}

export async function fetchVipDetail(puuid: string) {
  const res = await fetch(`${API}/vip/${puuid}`);
  if (!res.ok) throw new Error("Failed to fetch VIP detail");
  return res.json();
}