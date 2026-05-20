׳” ׳׳ ׳¢׳•׳‘׳“ ׳׳×׳” ׳׳ ׳׳¨׳™׳¥ ׳׳× ׳”׳‘׳“׳™׳§׳” ׳›׳׳• ׳©׳¦׳¨׳™׳
׳©׳™׳׳‘ ׳׳‘ ׳׳‘׳¢׳™׳•׳× ׳•׳”׳˜׳¢׳•׳™׳•׳× ׳©׳׳ ׳©׳׳©׳ ׳™׳ ׳©׳₪׳” ׳›׳ ׳”׳׳¢׳¨׳›׳× ׳׳©׳ ׳” ׳׳× ׳©׳₪׳” ׳©׳׳” ׳‘׳׳•׳₪׳ ׳׳•׳˜׳•׳׳˜׳™ ׳”׳›׳ ׳׳©׳×׳ ׳” ׳׳™ ׳׳₪׳©׳¨ ׳©׳™׳”׳™׳” ׳¢׳‘׳¨׳™׳× ׳׳™׳₪׳” ׳©׳™׳© ׳׳ ׳’׳׳™׳× 
׳•׳׳’׳‘׳™ ׳›׳ ׳©׳׳¨ ׳”׳©׳₪׳•׳× 

׳×׳¨׳™׳¥ ׳¡׳•׳›׳ ׳‘׳“׳™׳§׳” ׳׳—׳•׳“׳© ׳›׳™ ׳–׳” ׳׳ ׳×׳§׳™׳ ׳›׳›׳” 

׳‘׳ ׳•׳¡׳£

import React from "react";
import {
  Search,
  Bell,
  Grid3X3,
  Shield,
  Sparkles,
  Brain,
  Globe2,
  SlidersHorizontal,
  Home,
  BarChart3,
  TrendingUp,
  Activity,
  Newspaper,
  Gauge,
  FileText,
  Terminal,
  MonitorCog,
  ChevronDown,
  ChevronRight,
  Settings,
  User,
  Zap,
  CircleDollarSign,
  LineChart,
  Lock,
} from "lucide-react";

/**
 * EMPIREX OS ג€” Hedge Fund Command Center Dashboard
 * Single-file React + Tailwind implementation
 * RTL Hebrew UI
 */

const cn = (...classes) => classes.filter(Boolean).join(" ");

const marketTape = [
  { label: "S&P 500", value: "5,432.18", change: "+0.62%", positive: true },
  { label: "NASDAQ 100", value: "19,092.35", change: "+0.81%", positive: true },
  { label: "DOW JONES", value: "38,872.86", change: "+0.35%", positive: true },
  { label: "NIKKEI 225", value: "39,134.68", change: "+1.02%", positive: true },
  { label: "DXY", value: "104.21", change: "-0.24%", positive: false },
  { label: "GOLD", value: "$2,387.30", change: "+0.71%", positive: true },
  { label: "OIL WTI", value: "$77.41", change: "-0.18%", positive: false },
];

const heatmap = [
  { ticker: "AAPL", change: "+1.28%", size: "col-span-2 row-span-2", tone: "bg-emerald-600/80" },
  { ticker: "MSFT", change: "+0.91%", size: "col-span-2 row-span-2", tone: "bg-emerald-700/75" },
  { ticker: "NVDA", change: "+2.31%", size: "col-span-2 row-span-2", tone: "bg-emerald-500/85" },
  { ticker: "GOOGL", change: "+1.05%", size: "col-span-1 row-span-1", tone: "bg-emerald-700/70" },
  { ticker: "AMZN", change: "+0.72%", size: "col-span-1 row-span-1", tone: "bg-emerald-800/70" },
  { ticker: "META", change: "+1.18%", size: "col-span-1 row-span-1", tone: "bg-emerald-600/75" },
  { ticker: "TSLA", change: "-0.35%", size: "col-span-2 row-span-1", tone: "bg-rose-900/70" },
  { ticker: "BRK.B", change: "+0.40%", size: "col-span-1 row-span-1", tone: "bg-emerald-900/65" },
  { ticker: "JPM", change: "+0.31%", size: "col-span-1 row-span-1", tone: "bg-emerald-800/65" },
  { ticker: "V", change: "+0.55%", size: "col-span-1 row-span-1", tone: "bg-emerald-700/60" },
  { ticker: "AMD", change: "+0.42%", size: "col-span-1 row-span-1", tone: "bg-emerald-700/60" },
  { ticker: "WMT", change: "-0.15%", size: "col-span-1 row-span-1", tone: "bg-rose-950/75" },
];

const fxCards = [
  {
    symbol: "GBP/NZD",
    name: "Great British Pound / New Zealand Dollar",
    price: "2.2928",
    change: "+0.65%",
    positive: true,
    spark: "M0,58 C35,38 64,60 100,34 C138,8 176,35 220,18 C264,5 295,29 340,22",
  },
  {
    symbol: "GBP/AUD",
    name: "Great British Pound / Australian Dollar",
    price: "1.8826",
    change: "-0.10%",
    positive: false,
    spark: "M0,34 C34,18 72,42 104,24 C145,0 168,40 210,22 C260,6 286,36 340,18",
  },
  {
    symbol: "GBP/JPY",
    name: "Great British Pound / Japanese Yen",
    price: "212.91",
    change: "-0.07%",
    positive: false,
    spark: "M0,38 C42,48 64,18 108,30 C150,43 176,18 220,28 C262,40 300,20 340,33",
  },
];

const growthCards = [
  {
    symbol: "NXXT",
    name: "NextNRG, Inc.",
    price: "$0.82",
    change: "+100.02%",
    positive: true,
    spark: "M0,64 C40,58 72,50 112,44 C154,38 184,26 226,18 C270,8 304,28 340,12",
  },
  {
    symbol: "GIPR",
    name: "Generation Income Properties Inc.",
    price: "$0.43",
    change: "+75.89%",
    positive: true,
    spark: "M0,48 C36,58 72,34 108,42 C148,52 176,18 218,28 C260,40 296,20 340,30",
  },
  {
    symbol: "HAO",
    name: "Haoxi Health Technology Limited",
    price: "$0.01",
    change: "-21.35%",
    positive: false,
    spark: "M0,18 C34,26 64,30 100,34 C142,40 180,42 220,50 C260,58 300,52 340,62",
  },
];

const watchlist = [
  { symbol: "AAPL", name: "Apple Inc.", price: "193.27", change: "+1.28%", positive: true },
  { symbol: "NVDA", name: "NVIDIA Corporation", price: "1,142.45", change: "+2.31%", positive: true },
  { symbol: "TSLA", name: "Tesla, Inc.", price: "181.19", change: "-0.35%", positive: false },
  { symbol: "GOOGL", name: "Alphabet Inc.", price: "169.81", change: "+1.05%", positive: true },
  { symbol: "AMD", name: "Advanced Micro Devices", price: "165.32", change: "+0.42%", positive: true },
];

const toolCards = [
  {
    title: "׳¡׳•׳¨׳§ ׳”׳–׳“׳׳ ׳•׳™׳•׳×",
    desc: "׳׳™׳×׳•׳¨ ׳׳ ׳™׳•׳× ׳•׳ ׳›׳¡׳™׳ ׳¢׳ ׳₪׳•׳˜׳ ׳¦׳™׳׳ ׳¦׳׳™׳—׳” ׳‘׳׳‘׳ ׳” ׳©׳׳.",
    icon: Search,
  },
  {
    title: "׳”׳×׳¨׳׳•׳× ׳—׳›׳׳•׳×",
    desc: "׳§׳‘׳ ׳”׳×׳¨׳׳•׳× ׳׳•׳×׳׳׳•׳× ׳׳©׳•׳•׳§׳™׳ ׳•׳׳×׳™׳§ ׳©׳׳.",
    icon: Bell,
  },
  {
    title: "׳‘׳“׳™׳§׳× ׳×׳™׳§",
    desc: "׳ ׳™׳×׳•׳— ׳¡׳™׳›׳•׳ ׳™׳ ׳•׳×׳©׳•׳׳•׳× ׳©׳ ׳”׳×׳™׳§ ׳‘׳–׳׳ ׳׳׳×.",
    icon: Shield,
  },
  {
    title: "׳”׳©׳•׳•׳׳× ׳ ׳›׳¡׳™׳",
    desc: "׳”׳©׳•׳•׳” ׳‘׳™׳¦׳•׳¢׳™׳ ׳‘׳™׳ ׳ ׳›׳¡׳™׳, ׳׳“׳“׳™׳ ׳•׳¡׳§׳˜׳•׳¨׳™׳.",
    icon: BarChart3,
  },
];

const news = [
  {
    time: "11:05",
    title: "׳”׳“׳•׳׳¨ ׳׳×׳™׳™׳¦׳‘ ׳¡׳‘׳™׳‘ ׳”׳¨׳׳•׳× ׳”׳’׳‘׳•׳”׳•׳× ׳‘׳¢׳§׳‘׳•׳× ׳ ׳×׳•׳ ׳™ ׳׳™׳ ׳₪׳׳¦׳™׳”",
    source: "Bloomberg",
  },
  {
    time: "10:42",
    title: "׳׳ ׳™׳•׳× ׳”׳˜׳›׳ ׳•׳׳•׳’׳™׳” ׳׳•׳‘׳™׳׳•׳× ׳׳× ׳”׳¢׳׳™׳•׳× ׳‘׳•׳•׳ ׳¡׳˜׳¨׳™׳˜",
    source: "Reuters",
  },
];

function StatusDot({ className = "" }) {
  return <span className={cn("h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_14px_rgba(52,211,153,.9)]", className)} />;
}

function Panel({ children, className = "" }) {
  return (
    <div
      className={cn(
        "rounded-[22px] border border-white/10 bg-slate-950/58 shadow-[0_24px_80px_rgba(0,0,0,.45)] backdrop-blur-xl",
        className
      )}
    >
      {children}
    </div>
  );
}

function Sparkline({ path, positive = true, className = "" }) {
  return (
    <svg viewBox="0 0 340 80" className={cn("h-16 w-full overflow-visible", className)} preserveAspectRatio="none">
      <defs>
        <linearGradient id={`line-${positive ? "up" : "down"}`} x1="0" x2="1">
          <stop offset="0%" stopColor={positive ? "#22c55e" : "#ef4444"} stopOpacity="0.15" />
          <stop offset="45%" stopColor="#38bdf8" stopOpacity="0.95" />
          <stop offset="100%" stopColor={positive ? "#22c55e" : "#f87171"} stopOpacity="0.95" />
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2.3" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <path d={path} fill="none" stroke={`url(#line-${positive ? "up" : "down"})`} strokeWidth="3" filter="url(#glow)" />
      <path d={path} fill="none" stroke={positive ? "#22c55e" : "#ef4444"} strokeOpacity="0.28" strokeWidth="1" />
    </svg>
  );
}

function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/8 bg-[#050914]/88 backdrop-blur-2xl">
      <div className="mx-auto flex h-[76px] max-w-[1540px] items-center gap-4 px-6">
        <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.035] px-3 py-2 shadow-inner">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br from-cyan-500/30 to-blue-700/30 ring-1 ring-cyan-300/25">
            <User className="h-5 w-5 text-cyan-200" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold text-white">׳™׳©׳¨׳׳</div>
            <div className="text-xs text-slate-400">
              OS Trader <span className="text-emerald-400">Pro</span>
            </div>
          </div>
          <ChevronDown className="h-4 w-4 text-slate-500" />
        </div>

        <button className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.035] text-slate-300 transition hover:border-cyan-300/30 hover:text-white">
          <Bell className="h-4 w-4" />
        </button>

        <div className="hidden min-w-[280px] items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.035] px-4 py-3 text-slate-400 md:flex">
          <Search className="h-4 w-4" />
          <span className="text-sm">׳—׳™׳₪׳•׳© ׳׳ ׳™׳”, ׳׳“׳“, ׳׳• ׳ ׳•׳©׳...</span>
        </div>

        <nav className="mx-auto hidden items-center gap-1 rounded-2xl border border-white/10 bg-white/[0.03] p-1 lg:flex">
          {[
            ["׳׳‘׳˜ ׳›׳׳׳™", Globe2],
            ["׳¡׳§׳™׳¨׳”", BarChart3],
            ["׳”׳×׳¨׳׳•׳×", Bell],
            ["׳×׳™׳§ ׳׳¢׳§׳‘", Activity],
            ["AI Agent", Sparkles],
            ["׳¡׳•׳¨׳§", Search],
            ["׳—׳“׳©׳•׳×", Newspaper],
            ["׳©׳•׳§", LineChart],
          ].map(([label, Icon]) => (
            <button
              key={label}
              className={cn(
                "flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm text-slate-300 transition hover:bg-white/[0.06] hover:text-white",
                label === "AI Agent" && "bg-cyan-500/10 text-cyan-300 shadow-[0_0_25px_rgba(6,182,212,.12)]"
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <button className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.035] text-slate-300 transition hover:border-cyan-300/30 hover:text-white">
          <Grid3X3 className="h-4 w-4" />
        </button>

        <div className="flex items-center gap-3 pr-1">
          <div className="relative flex h-10 w-10 items-center justify-center">
            <div className="absolute inset-0 rounded-xl bg-blue-500/25 blur-md" />
            <div className="relative h-8 w-8 rotate-45 rounded-lg border border-cyan-300/40 bg-gradient-to-br from-blue-600 to-cyan-400 shadow-[0_0_22px_rgba(56,189,248,.35)]" />
          </div>

          <div className="leading-none">
            <div className="tracking-[0.45em] text-white">EMPIREX</div>
            <div className="mt-2 text-sm font-black tracking-[0.45em] text-cyan-400">OS</div>
          </div>
        </div>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-white/8">
      <div className="absolute inset-0">
        <div className="absolute left-0 top-0 h-[330px] w-[460px] rounded-full bg-blue-700/20 blur-[90px]" />
        <div className="absolute right-[20%] top-[10%] h-[260px] w-[520px] rounded-full bg-cyan-500/10 blur-[100px]" />
        <div className="absolute inset-0 opacity-[0.18] [background-image:linear-gradient(rgba(255,255,255,.08)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.08)_1px,transparent_1px)] [background-size:44px_44px]" />
        <div className="absolute left-12 top-20 hidden h-56 w-56 rounded-full border border-cyan-300/20 bg-[radial-gradient(circle_at_40%_30%,rgba(59,130,246,.45),transparent_38%),radial-gradient(circle_at_50%_50%,rgba(15,23,42,.6),rgba(2,6,23,.2)_70%)] shadow-[0_0_80px_rgba(56,189,248,.25)] lg:block" />
        <div className="absolute left-[280px] top-24 hidden h-56 w-[520px] opacity-30 lg:block">
          <div className="h-full w-full bg-[linear-gradient(90deg,transparent,rgba(59,130,246,.35),transparent)] blur-sm" />
        </div>
        <div className="absolute right-24 top-24 hidden h-44 w-96 opacity-20 xl:block">
          <svg viewBox="0 0 600 240" className="h-full w-full">
            <path
              d="M0,160 C50,120 90,140 140,90 C190,40 220,75 270,50 C330,20 360,90 410,60 C470,24 520,70 600,30"
              fill="none"
              stroke="#38bdf8"
              strokeWidth="4"
              opacity=".55"
            />
          </svg>
        </div>
      </div>

      <div className="relative mx-auto max-w-[1540px] px-6 pb-7 pt-8">
        <div className="mx-auto flex w-fit items-center gap-3 rounded-full border border-white/10 bg-black/25 px-5 py-2 text-xs font-bold uppercase tracking-[0.45em] text-slate-300">
          COMMAND CENTER ONLINE
          <StatusDot />
        </div>

        <div className="mt-6 text-center">
          <h1 className="text-5xl font-black tracking-tight text-white md:text-7xl">
            ׳‘׳¨׳•׳ ׳”׳‘׳, <span className="bg-gradient-to-l from-cyan-300 via-blue-400 to-blue-700 bg-clip-text text-transparent">׳“׳ ׳™׳׳</span>.
          </h1>

          <p className="mx-auto mt-5 max-w-3xl text-lg leading-8 text-slate-300">
            ׳›׳׳ ׳׳ ׳•׳”׳׳× ׳¡׳‘׳™׳‘׳× ׳”׳¢׳‘׳•׳“׳” ׳©׳׳ ג€” ׳׳—׳•׳‘׳¨׳× ׳׳ ׳×׳•׳ ׳™ ׳©׳•׳§ ׳—׳™׳™׳, ׳ ׳™׳×׳•׳— ׳׳×׳§׳“׳,
            <br className="hidden md:block" />
            AI Agent ׳•׳×׳•׳‘׳ ׳•׳×. ׳¡׳™׳›׳•׳ ׳׳ ׳•׳”׳, ׳”׳—׳׳˜׳•׳× ׳׳”׳™׳¨׳•׳× ג€” ׳”׳›׳ ׳‘׳׳§׳•׳ ׳׳—׳“.
          </p>

          <div className="mt-7 flex flex-wrap items-center justify-center gap-4">
            <button className="group flex items-center gap-3 rounded-2xl border border-white/12 bg-white/[0.04] px-7 py-3.5 text-sm font-bold text-white transition hover:border-cyan-300/40 hover:bg-white/[0.07]">
              <Shield className="h-4 w-4 text-cyan-300" />
              ׳¡׳§׳•׳¨ ׳׳× ׳”׳×׳™׳§
            </button>

            <button className="group flex items-center gap-3 rounded-2xl border border-white/12 bg-white/[0.04] px-7 py-3.5 text-sm font-bold text-white transition hover:border-cyan-300/40 hover:bg-white/[0.07]">
              <Gauge className="h-4 w-4 text-cyan-300" />
              Risk Engine
            </button>

            <button className="group flex items-center gap-3 rounded-2xl border border-cyan-300/30 bg-gradient-to-l from-blue-600 to-cyan-500 px-7 py-3.5 text-sm font-black text-white shadow-[0_0_35px_rgba(37,99,235,.45)] transition hover:scale-[1.02]">
              <Sparkles className="h-4 w-4" />
              ׳”׳×׳—׳ ׳¦׳³׳׳˜ ׳¢׳ AI Agent
            </button>
          </div>
        </div>

        <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-t border-white/8 pt-5 text-sm">
          <div className="flex items-center gap-3 text-slate-400">
            <span>׳¢׳“׳›׳•׳ ׳׳—׳¨׳•׳: 11:18:27</span>
            <span className="h-4 w-px bg-white/15" />
            <span>API ׳׳—׳•׳‘׳¨</span>
            <span className="h-4 w-px bg-white/15" />
            <span>׳׳¦׳‘ ׳׳¢׳¨׳›׳× ׳×׳§׳™׳</span>
          </div>

          <div className="flex items-center gap-2 font-bold text-emerald-400">
            LIVE <StatusDot />
          </div>
        </div>
      </div>
    </section>
  );
}

function Tape() {
  return (
    <div className="border-b border-white/8 bg-[#050914]/78 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1540px] items-center overflow-hidden px-6">
        <div className="flex min-w-max animate-none items-center">
          {marketTape.map((item, index) => (
            <div key={item.label} className="flex items-center gap-4 border-l border-white/10 px-8 py-4 first:border-r">
              <span className="text-sm font-bold text-slate-200">{item.label}</span>
              <span className="text-sm text-slate-400">{item.value}</span>
              <span className={cn("text-sm font-bold", item.positive ? "text-emerald-400" : "text-rose-400")}>
                {item.change}
              </span>
              {index !== marketTape.length - 1 && <span className="h-5 w-px bg-white/10" />}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SearchControls() {
  return (
    <div className="mx-auto mt-5 flex max-w-[1540px] flex-col gap-4 px-6 lg:flex-row lg:items-center">
      <button className="flex w-fit items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.04] px-5 py-3 text-sm font-bold text-slate-200">
        ׳¢׳¨׳•׳ ׳׳¡׳
        <SlidersHorizontal className="h-4 w-4 text-cyan-300" />
      </button>

      <div className="flex flex-1 items-center gap-3 rounded-2xl border border-white/10 bg-slate-950/55 px-4 py-3 shadow-inner">
        <Search className="h-5 w-5 text-slate-500" />
        <input
          dir="rtl"
          placeholder="׳—׳™׳₪׳•׳© ׳׳ ׳™׳”, ׳׳“׳“, ׳׳˜׳‘׳¢ ׳׳• ׳ ׳•׳©׳..."
          className="w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-500"
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {["׳”׳›׳", "׳׳•׳¢׳“׳₪׳™׳", "׳׳¨׳”׳´׳‘", "׳™׳©׳¨׳׳", "׳¡׳—׳•׳¨׳•׳×", "׳׳˜׳´׳—"].map((f) => (
          <button
            key={f}
            className={cn(
              "rounded-xl border px-5 py-3 text-sm font-bold transition",
              f === "׳”׳›׳"
                ? "border-blue-400/40 bg-blue-600/20 text-blue-200 shadow-[0_0_20px_rgba(37,99,235,.18)]"
                : "border-white/10 bg-white/[0.035] text-slate-400 hover:text-white"
            )}
          >
            {f}
          </button>
        ))}
      </div>
    </div>
  );
}

function MarketCard({ item }) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-white/10 bg-[#07101f]/80 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,.04)] transition hover:-translate-y-0.5 hover:border-cyan-300/30 hover:bg-[#091629]">
      <div className="absolute inset-0 bg-gradient-to-br from-white/[0.035] to-transparent opacity-0 transition group-hover:opacity-100" />

      <div className="relative flex items-start justify-between gap-4">
        <div className="w-1/2">
          <Sparkline path={item.spark} positive={item.positive} />
        </div>

        <div className="text-left">
          <div className="flex items-center justify-end gap-2 text-xs font-black text-slate-300">
            LIVE <StatusDot />
          </div>
          <h3 className="mt-4 text-2xl font-black tracking-wide text-white">{item.symbol}</h3>
          <p className="mt-1 text-xs text-slate-400">{item.name}</p>
        </div>
      </div>

      <div className="relative mt-4 flex items-end justify-between">
        <span
          className={cn(
            "rounded-xl px-3 py-1.5 text-sm font-black",
            item.positive ? "bg-emerald-500/13 text-emerald-400" : "bg-rose-500/12 text-rose-400"
          )}
        >
          {item.change}
        </span>

        <div className="text-left">
          <div className="text-3xl font-black tracking-wide text-white">{item.price}</div>
          {item.price.includes("$") && <div className="mt-1 text-xs font-bold text-slate-500">USD</div>}
        </div>
      </div>
    </div>
  );
}

function MarketHeatmap() {
  return (
    <Panel className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-black text-white">Market Heatmap</h3>
          <p className="mt-1 text-xs text-slate-500">S&P 500</p>
        </div>
        <StatusDot />
      </div>

      <div className="grid h-[270px] grid-cols-6 grid-rows-5 gap-1">
        {heatmap.map((item) => (
          <div
            key={item.ticker}
            className={cn(
              "flex flex-col justify-center rounded-lg p-2 text-center shadow-inner ring-1 ring-white/8",
              item.size,
              item.tone
            )}
          >
            <div className="text-lg font-black text-white">{item.ticker}</div>
            <div className="text-xs font-bold text-white/85">{item.change}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
        <span>-2%</span>
        <div className="mx-3 h-2 flex-1 rounded-full bg-gradient-to-l from-emerald-500 via-slate-700 to-rose-600" />
        <span>+2%</span>
      </div>
    </Panel>
  );
}

function MarketPulse() {
  return (
    <Panel className="p-6">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-black text-white">AI Market Pulse</h3>
          <p className="mt-1 text-xs text-slate-500">׳ ׳™׳×׳•׳— ׳׳•׳׳ ׳˜׳•׳ ׳¨׳•׳—׳‘׳™</p>
        </div>
        <StatusDot />
      </div>

      <div className="mt-6 flex items-center gap-6">
        <div className="relative flex h-32 w-32 shrink-0 items-center justify-center rounded-full bg-[conic-gradient(from_90deg,#22c55e_0_74%,rgba(255,255,255,.09)_74%_100%)] shadow-[0_0_42px_rgba(34,197,94,.25)]">
          <div className="absolute inset-3 rounded-full bg-[#07101f]" />
          <div className="relative text-center">
            <div className="text-4xl font-black text-white">74</div>
            <div className="text-sm font-black text-emerald-400">Bullish</div>
          </div>
        </div>

        <div>
          <h4 className="text-xl font-black text-emerald-400">׳׳•׳׳ ׳˜׳•׳ ׳—׳™׳•׳‘׳™</h4>
          <p className="mt-3 text-sm leading-7 text-slate-400">
            ׳¨׳•׳—׳‘ ׳”׳©׳•׳§ ׳‘׳׳•׳׳ ׳˜׳•׳ ׳—׳™׳•׳‘׳™, ׳¢׳ ׳׳’׳׳•׳× ׳—׳–׳§׳•׳× ׳‘׳׳ ׳™׳•׳× ׳˜׳›׳ ׳•׳׳•׳’׳™׳” ׳•׳¦׳׳™׳—׳”.
          </p>
          <button className="mt-4 rounded-xl border border-cyan-300/20 bg-cyan-500/8 px-4 py-2 text-sm font-bold text-cyan-300">
            ׳¡׳§׳•׳¨ ׳ ׳™׳×׳•׳— ׳׳׳
          </button>
        </div>
      </div>
    </Panel>
  );
}

function WatchlistPanel() {
  return (
    <Panel className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-black text-white">׳×׳™׳§ ׳׳¢׳§׳‘</h3>
          <p className="mt-1 text-xs text-slate-500">API ֲ· ׳¨׳©׳™׳׳× ׳ ׳›׳¡׳™׳ ׳₪׳¢׳™׳׳”</p>
        </div>
        <StatusDot />
      </div>

      <div className="space-y-3">
        {watchlist.map((row) => (
          <div key={row.symbol} className="grid grid-cols-[1fr_auto_auto] items-center gap-4 rounded-xl border border-white/7 bg-white/[0.025] px-4 py-3">
            <div>
              <div className="font-black text-white">{row.symbol}</div>
              <div className="text-xs text-slate-500">{row.name}</div>
            </div>

            <div className={cn("text-sm font-black", row.positive ? "text-emerald-400" : "text-rose-400")}>{row.change}</div>
            <div className="text-sm font-bold text-slate-300">{row.price}</div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function NewsPanel() {
  return (
    <Panel className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-black text-white">׳—׳“׳©׳•׳× ׳©׳•׳§</h3>
        <Newspaper className="h-4 w-4 text-cyan-300" />
      </div>

      <div className="space-y-3">
        {news.map((item) => (
          <div key={item.time} className="flex gap-3 rounded-xl border border-white/7 bg-white/[0.025] p-3">
            <div className="h-16 w-20 shrink-0 rounded-xl bg-gradient-to-br from-blue-700/50 via-slate-900 to-rose-900/30" />
            <div className="flex-1">
              <div className="flex justify-between gap-3 text-xs text-slate-500">
                <span>{item.time}</span>
                <span>{item.source}</span>
              </div>
              <div className="mt-2 text-sm font-bold leading-6 text-slate-200">{item.title}</div>
            </div>
          </div>
        ))}
      </div>

      <button className="mt-4 w-full rounded-xl border border-white/10 bg-white/[0.035] py-3 text-sm font-bold text-cyan-300">
        ׳¦׳₪׳” ׳‘׳›׳ ׳”׳—׳“׳©׳•׳×
      </button>
    </Panel>
  );
}

function ToolCard({ item, index }) {
  const Icon = item.icon;

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/55 p-5 transition hover:border-cyan-300/25 hover:bg-white/[0.045]">
      <div className="mb-5 flex items-center justify-between">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-cyan-300/15 bg-cyan-500/8 text-cyan-300">
          <Icon className="h-5 w-5" />
        </div>
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-cyan-500 text-sm font-black text-white shadow-[0_0_18px_rgba(6,182,212,.4)]">
          {index + 1}
        </span>
      </div>

      <h4 className="text-lg font-black text-white">{item.title}</h4>
      <p className="mt-2 text-sm leading-6 text-slate-400">{item.desc}</p>
    </div>
  );
}

function MainDashboard() {
  return (
    <main className="mx-auto grid max-w-[1540px] grid-cols-12 gap-5 px-6 pb-7 pt-5">
      <aside className="col-span-12 space-y-5 xl:col-span-3">
        <MarketHeatmap />
        <NewsPanel />
      </aside>

      <section className="col-span-12 space-y-5 xl:col-span-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {fxCards.map((item) => (
            <MarketCard key={item.symbol} item={item} />
          ))}
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {growthCards.map((item) => (
            <MarketCard key={item.symbol} item={item} />
          ))}
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          {toolCards.map((item, index) => (
            <ToolCard key={item.title} item={item} index={index} />
          ))}
        </div>
      </section>

      <aside className="col-span-12 space-y-5 xl:col-span-3">
        <MarketPulse />
        <WatchlistPanel />

        <Panel className="overflow-hidden p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-black text-white">Risk Engine</h3>
            <StatusDot />
          </div>

          <div className="mt-6 flex items-center gap-5">
            <div className="relative flex h-28 w-28 shrink-0 items-center justify-center rounded-full bg-[conic-gradient(from_140deg,#f97316_0_24%,#facc15_24%_48%,#22c55e_48%_72%,rgba(255,255,255,.08)_72%_100%)]">
              <div className="absolute inset-3 rounded-full bg-[#07101f]" />
              <div className="relative text-center">
                <div className="text-3xl font-black text-white">72</div>
                <div className="text-xs text-slate-500">Risk Score</div>
              </div>
            </div>

            <div className="flex-1 space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-400">׳—׳©׳™׳₪׳× ׳©׳•׳§</span>
                <span className="font-black text-yellow-400">׳‘׳™׳ ׳•׳ ׳™</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">׳¡׳™׳›׳•׳ ׳׳©׳¨׳׳™</span>
                <span className="font-black text-emerald-400">׳ ׳׳•׳</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">׳¡׳™׳›׳•׳ ׳ ׳–׳™׳׳•׳×</span>
                <span className="font-black text-yellow-400">׳‘׳™׳ ׳•׳ ׳™</span>
              </div>
            </div>
          </div>
        </Panel>
      </aside>

      <section className="col-span-12">
        <Panel className="overflow-hidden">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px]">
            <div className="relative p-6">
              <div className="absolute inset-y-0 left-0 w-80 bg-gradient-to-r from-cyan-500/13 to-transparent" />
              <div className="relative">
                <div className="flex items-center gap-3">
                  <Sparkles className="h-5 w-5 text-cyan-300" />
                  <h3 className="text-xl font-black text-white">AI Insight</h3>
                </div>

                <p className="mt-4 max-w-4xl text-base leading-8 text-slate-300">
                  ׳×׳•׳‘׳ ׳” ׳׳¨׳›׳–׳™׳× ׳¢׳‘׳•׳¨׳: ׳”׳׳•׳׳ ׳˜׳•׳ ׳‘׳׳ ׳™׳•׳× ׳”׳¦׳׳™׳—׳” ׳׳×׳—׳–׳§, ׳¢׳ ׳¢׳ ׳™׳™׳ ׳’׳‘׳•׳” ׳‘׳¡׳§׳˜׳•׳¨
                  ׳”׳˜׳›׳ ׳•׳׳•׳’׳™׳” ׳•׳”׳׳ ׳¨׳’׳™׳” ׳”׳׳×׳—׳“׳©׳×. ׳׳•׳׳׳¥ ׳׳¢׳§׳•׳‘ ׳׳—׳¨׳™ ׳ ׳×׳•׳ ׳™ CPI ׳”׳§׳¨׳•׳‘׳™׳ ׳•׳׳‘׳“׳•׳§ ׳—׳©׳™׳₪׳”
                  ׳׳—׳•׳“׳©׳× ׳׳ ׳›׳¡׳™׳ ׳¨׳’׳™׳©׳™׳ ׳׳“׳•׳׳¨.
                </p>
              </div>
            </div>

            <div className="relative min-h-[150px] border-t border-white/8 bg-blue-500/5 lg:border-r lg:border-t-0">
              <svg viewBox="0 0 460 180" className="absolute inset-0 h-full w-full opacity-80" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="aiChart" x1="0" x2="1">
                    <stop offset="0%" stopColor="#0f172a" />
                    <stop offset="100%" stopColor="#38bdf8" />
                  </linearGradient>
                </defs>
                <path d="M0,150 C40,140 58,122 96,130 C150,144 170,80 220,90 C270,100 292,44 340,62 C386,78 408,30 460,42" fill="none" stroke="#38bdf8" strokeWidth="3" />
                <path d="M0,150 C40,140 58,122 96,130 C150,144 170,80 220,90 C270,100 292,44 340,62 C386,78 408,30 460,42 L460,180 L0,180 Z" fill="url(#aiChart)" opacity=".18" />
              </svg>
            </div>
          </div>
        </Panel>
      </section>
    </main>
  );
}

function Footer() {
  return (
    <footer className="border-t border-white/8 bg-[#050914]/88">
      <div className="mx-auto flex max-w-[1540px] flex-wrap items-center justify-between gap-4 px-6 py-5 text-sm">
        <div className="flex items-center gap-4">
          <span className="font-bold text-slate-500">EMPIREX OS v2.10.0</span>
          <span className="flex items-center gap-2 text-emerald-400">
            <StatusDot />
            ׳›׳ ׳”׳׳¢׳¨׳›׳•׳× ׳₪׳•׳¢׳׳•׳×
          </span>
        </div>

        <div className="text-slate-500">11:18:27 (IST)</div>

        <div className="flex items-center gap-6 text-slate-500">
          <button>׳×׳׳™׳›׳”</button>
          <button>׳₪׳¨׳˜׳™׳•׳×</button>
          <button>׳×׳ ׳׳™ ׳©׳™׳׳•׳©</button>
          <button className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.035] px-4 py-2 text-slate-300">
            ׳”׳’׳“׳¨׳•׳× ׳׳¢׳¨׳›׳×
            <Settings className="h-4 w-4" />
          </button>
        </div>
      </div>
    </footer>
  );
}

export default function App() {
  return (
    <div dir="rtl" className="min-h-screen bg-[#030712] text-white selection:bg-cyan-400/30">
      <div className="pointer-events-none fixed inset-0 z-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(37,99,235,.18),transparent_34%),radial-gradient(circle_at_85%_25%,rgba(6,182,212,.13),transparent_32%),linear-gradient(180deg,#050914_0%,#020617_100%)]" />
        <div className="absolute inset-0 opacity-[0.12] [background-image:linear-gradient(rgba(255,255,255,.08)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.08)_1px,transparent_1px)] [background-size:42px_42px]" />
      </div>

      <div className="relative z-10">
        <Header />
        <Hero />
        <Tape />
        <SearchControls />
        <MainDashboard />
        <Footer />
      </div>

      <button className="fixed bottom-7 left-7 z-50 flex items-center gap-3 rounded-2xl border border-emerald-300/20 bg-slate-950/85 px-5 py-4 text-sm font-black text-white shadow-[0_0_50px_rgba(16,185,129,.22)] backdrop-blur-xl transition hover:scale-[1.02]">
        AI Assistant
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/20 text-emerald-300">
          <Brain className="h-5 w-5" />
        </span>
      </button>
    </div>
  );
}

׳–׳” ׳”׳§׳•׳“ ׳”׳—׳“׳©׳׳“׳£ ׳”׳‘׳™׳× ׳×׳•׳•׳“׳ ׳©׳–׳” ׳—׳™ ׳×׳”׳₪׳•׳ ׳׳•׳×׳• ׳׳§׳•׳“ ׳—׳™׳” ׳–׳” ׳§׳•׳“ ׳׳×׳׳•׳ ׳”

׳×׳‘׳¦׳¢ ׳§׳•׳ ׳׳× ׳”׳©׳™׳ ׳•׳™ ׳‘׳׳¡׳ ׳”׳‘׳™׳× ׳׳—׳¨׳™ ׳–׳” ׳×׳¨׳™׳¥ ׳¡׳•׳›׳ ׳׳‘׳“׳™׳§׳” ׳¢׳׳•׳§׳” ׳׳’׳‘׳™ ׳©׳™׳ ׳•׳™ ׳©׳₪׳•׳× 
