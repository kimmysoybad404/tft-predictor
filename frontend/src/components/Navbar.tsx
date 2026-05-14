"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import SettingsMenu from "./Settingmenu";

const links = [
  { href: "/",          label: "Meta"      },
  { href: "/tier-list", label: "Tier List" },
  { href: "/predict",   label: "Predict"   },
  { href: "/vip",       label: "VIP"       },
];

export default function Navbar() {
  const path = usePathname();
  return (
    <nav className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 sticky top-0 z-10 transition-colors">
      <div className="max-w-5xl mx-auto px-4 flex items-center gap-6 h-12">
        <span className="text-sm font-medium text-gray-900 dark:text-gray-100 mr-2">TFT Predictor</span>
        <div className="flex items-center gap-1 flex-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={clsx(
                "text-sm h-12 flex items-center px-1 border-b-2 transition-colors",
                path === l.href
                  ? "border-gray-900 dark:border-gray-100 text-gray-900 dark:text-gray-100 font-medium"
                  : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
              )}
            >
              {l.label}
            </Link>
          ))}
        </div>
        <SettingsMenu />
      </div>
    </nav>
  );
}