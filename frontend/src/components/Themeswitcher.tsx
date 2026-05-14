"use client";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

const options = [
  { value: "light",  label: "Light",  icon: "☀️" },
  { value: "dark",   label: "Dark",   icon: "🌙" },
  { value: "system", label: "System", icon: "💻" },
];

export default function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  if (!mounted) return <div className="w-24 h-7" />;

  return (
    <div className="flex items-center gap-0.5 bg-gray-100 dark:bg-gray-800 rounded-lg p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => setTheme(o.value)}
          title={o.label}
          className={`flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors ${
            theme === o.value
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm"
              : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
          }`}
        >
          <span style={{ fontSize: 12 }}>{o.icon}</span>
          <span className="hidden sm:inline">{o.label}</span>
        </button>
      ))}
    </div>
  );
}