// จัดกลุ่ม region ตามทวีป/โซนสำหรับ dropdown filter — ตอนนี้ ingestion ดึงแค่ 5 region นี้
export const REGION_GROUPS: { label: string; regions: string[] }[] = [
  { label: "Asia",     regions: ["kr", "sg2"] },
  { label: "Americas", regions: ["na1", "br1"] },
  { label: "Europe",   regions: ["euw1"] },
];

export const REGIONS = REGION_GROUPS.flatMap((g) => g.regions);
