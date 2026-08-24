"use client";
import { useTheme } from "next-themes";
import { useEffect, useState, useRef, useCallback } from "react";
import { fetchAdminStatus } from "@/lib/api";

const themes = [
  { value: "light",  label: "Light",  icon: "☀️" },
  { value: "dark",   label: "Dark",   icon: "🌙" },
  { value: "system", label: "System", icon: "💻" },
];

function timeAgo(iso: string | null): string {
  if (!iso) return "never";
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function SettingsMenu() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen]       = useState(false);
  const [mounted, setMounted] = useState(false);
  const [status, setStatus]   = useState<{
    riot_api_key_valid: boolean | null;
    last_ingested_at: string | null;
    data_retention_days?: number;
    counts?: { matches: number; participants: number; summoners: number };
    max_summoners?: number;
  } | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  const loadStatus = useCallback(() => {
    setStatusLoading(true);
    fetchAdminStatus().then(setStatus).catch(() => setStatus(null)).finally(() => setStatusLoading(false));
  }, []);

  // ปิด dropdown เมื่อคลิกข้างนอก
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  if (!mounted) return <div className="w-8 h-8" />;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => {
          setOpen((v) => {
            if (!v) loadStatus(); // โหลดสถานะใหม่ทุกครั้งที่เปิด กันข้อมูลค้าง
            return !v;
          });
        }}
        className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-surface-raised transition-colors"
        title="Settings"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065Z"
          />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-64 bg-white dark:bg-surface-card border border-gray-200 dark:border-surface-border rounded-xl shadow-lg py-1 z-50">
          <p className="text-xs text-gray-400 dark:text-gray-500 px-3 py-2 font-medium">Theme</p>
          {themes.map((t) => (
            <button
              key={t.value}
              onClick={() => { setTheme(t.value); setOpen(false); }}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm transition-colors ${
                theme === t.value
                  ? "text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-surface-raised"
                  : "text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-surface-raised"
              }`}
            >
              <span style={{ fontSize: 14 }}>{t.icon}</span>
              <span>{t.label}</span>
              {theme === t.value && (
                <svg className="ml-auto" width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                  <path d="M10 3L5 8.5 2 5.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
            </button>
          ))}

          <div className="border-t border-gray-100 dark:border-surface-border mt-1 pt-1">
            <p className="text-xs text-gray-400 dark:text-gray-500 px-3 py-2 font-medium">Data status</p>
            <div className="px-3 pb-2.5 space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">Riot API key</span>
                {statusLoading ? (
                  <span className="text-gray-400 dark:text-gray-600">checking…</span>
                ) : status?.riot_api_key_valid === true ? (
                  <span className="flex items-center gap-1 font-medium text-accent">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent" /> Active
                  </span>
                ) : status?.riot_api_key_valid === false ? (
                  <span className="flex items-center gap-1 font-medium text-red-500">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500" /> Expired
                  </span>
                ) : (
                  <span className="flex items-center gap-1 font-medium text-gray-400">
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400" /> Unknown
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">Last data ingested</span>
                <span className="text-gray-700 dark:text-gray-300">{statusLoading ? "…" : timeAgo(status?.last_ingested_at ?? null)}</span>
              </div>
            </div>
          </div>

          <div className="border-t border-gray-100 dark:border-surface-border mt-1 pt-1">
            <p className="text-xs text-gray-400 dark:text-gray-500 px-3 py-2 font-medium">Data collected</p>
            <div className="px-3 pb-2.5 space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">Matches</span>
                <span className="text-gray-700 dark:text-gray-300 tabular-nums">
                  {statusLoading ? "…" : (status?.counts?.matches ?? 0).toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">Participants</span>
                <span className="text-gray-700 dark:text-gray-300 tabular-nums">
                  {statusLoading ? "…" : (status?.counts?.participants ?? 0).toLocaleString()}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500 dark:text-gray-400">Summoners</span>
                <span className="text-gray-700 dark:text-gray-300 tabular-nums">
                  {statusLoading ? "…" : (status?.counts?.summoners ?? 0).toLocaleString()}
                  {!statusLoading && status?.max_summoners && (
                    <span className="text-gray-400 dark:text-gray-600"> / {status.max_summoners.toLocaleString()} max</span>
                  )}
                </span>
              </div>
              {!statusLoading && status?.data_retention_days != null && (
                <p className="text-[10px] text-gray-400 dark:text-gray-600 pt-0.5">
                  Matches & participants roll off after {status.data_retention_days} days (no fixed max)
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
