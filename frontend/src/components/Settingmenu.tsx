"use client";
import { useTheme } from "next-themes";
import { useEffect, useState, useRef } from "react";

const themes = [
  { value: "light",  label: "Light",  icon: "☀️" },
  { value: "dark",   label: "Dark",   icon: "🌙" },
  { value: "system", label: "System", icon: "💻" },
];

export default function SettingsMenu() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen]     = useState(false);
  const [mounted, setMounted] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

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
        onClick={() => setOpen((v) => !v)}
        className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        title="Settings"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="8" cy="8" r="2.5" />
          <path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3.05 3.05l1.06 1.06M11.89 11.89l1.06 1.06M3.05 12.95l1.06-1.06M11.89 4.11l1.06-1.06" strokeLinecap="round"/>
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-48 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg py-1 z-50">
          <p className="text-xs text-gray-400 dark:text-gray-500 px-3 py-2 font-medium">Theme</p>
          {themes.map((t) => (
            <button
              key={t.value}
              onClick={() => { setTheme(t.value); setOpen(false); }}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm transition-colors ${
                theme === t.value
                  ? "text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-800"
                  : "text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
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
        </div>
      )}
    </div>
  );
}