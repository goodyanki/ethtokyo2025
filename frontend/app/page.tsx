import Link from "next/link";
import { ArrowRight, QrCode, Send, Shield, Sparkles } from "lucide-react";

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-gradient-to-b from-white to-[#f7f9fc] text-[#0f172a]">
      {/* 背景装饰：柔光 + 网格 */}
      <div className="pointer-events-none absolute inset-0 [mask-image:radial-gradient(65%_50%_at_50%_0%,#000_50%,transparent_100%)]">
        <svg className="absolute inset-0 h-full w-full opacity-[0.08]" aria-hidden>
          <defs>
            <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M32 0 H0 V32" fill="none" stroke="currentColor" strokeWidth="0.6" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" className="text-slate-700" />
        </svg>
      </div>
      {/* 彩色光斑 */}
      <div className="pointer-events-none absolute -top-24 left-1/2 h-[420px] w-[620px] -translate-x-1/2 rounded-full bg-gradient-to-r from-indigo-400 via-sky-400 to-emerald-400 opacity-20 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 -left-28 h-[300px] w-[420px] rounded-full bg-gradient-to-tr from-fuchsia-400 via-pink-400 to-amber-300 opacity-20 blur-3xl" />
      <div className="pointer-events-none absolute top-24 -right-24 h-[260px] w-[360px] rounded-full bg-gradient-to-tr from-blue-500 to-purple-500 opacity-20 blur-3xl" />

      <div className="relative mx-auto max-w-6xl px-6 py-16">
        {/* 头部 */}
        <header className="mb-12 flex items-center justify-between gap-6">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 shadow-sm">
              <Sparkles className="h-3.5 w-3.5 text-amber-500" />
              live demo • stealth + mpc 2/3
            </div>
            <h1 className="mt-3 bg-gradient-to-r from-slate-900 via-slate-800 to-slate-700 bg-clip-text text-4xl font-semibold tracking-tight text-transparent">
              NomadPay
            </h1>
            <p className="mt-2 text-sm text-[#475569]">web3 · privacy · zk</p>
          </div>

          {/* 特性胶囊 */}
          <div className="hidden md:flex flex-wrap items-center gap-2">
            {["Non-custodial", "Stealth address", "MPC 2/3", "Optional audit"].map((t) => (
              <span
                key={t}
                className="inline-flex items-center rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 shadow-sm"
              >
                <Shield className="mr-1 h-3.5 w-3.5 text-emerald-500" />
                {t}
              </span>
            ))}
          </div>
        </header>

        {/* 主卡片 */}
        <section className="flex items-center justify-center">
          <div className="group relative w-[340px] sm:w-[360px] h-[560px]">
            {/* 外层渐变描边 */}
            <div className="absolute -inset-[1px] rounded-[26px] bg-gradient-to-br from-slate-200 via-slate-100 to-white opacity-90 group-hover:opacity-100 transition-opacity" />
            <div className="relative z-10 h-full rounded-[25px] border border-slate-200/80 bg-white/90 shadow-[0_12px_40px_rgba(15,23,42,0.08)] backdrop-blur-md">
              {/* 卡片内光晕 */}
              <div className="pointer-events-none absolute inset-0 rounded-[25px] [mask-image:radial-gradient(120%_80%_at_50%_-10%,#000_55%,transparent_85%)]">
                <div className="absolute inset-x-0 -top-20 mx-auto h-80 w-[90%] rounded-full bg-gradient-to-r from-indigo-400/25 via-sky-400/25 to-emerald-400/25 blur-2xl" />
              </div>

              <div className="relative flex h-full flex-col items-center justify-center gap-7 px-8">
                {/* 标题区 */}
                <div className="text-center">
                  <div className="text-lg font-medium text-slate-900">NomadPay</div>
                  <div className="mt-1 text-[12.5px] text-[#64748b]">Stealth • ZK • Light</div>
                </div>

                {/* 中心图标 */}
                <div className="relative">
                  <div className="absolute -inset-4 rounded-2xl bg-gradient-to-tr from-indigo-200/50 to-emerald-200/50 blur-2xl" />
                  <div className="relative flex h-24 w-24 items-center justify-center rounded-2xl border border-slate-200 bg-white shadow-md">
                    <QrCode className="h-10 w-10 text-slate-800" />
                  </div>
                </div>

                {/* 按钮区 */}
                <div className="mt-2 grid w-full max-w-[240px] gap-3">
                  <Link
                    href="/send"
                    className="group/btn inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-sky-500 to-sky-600 text-white shadow-lg transition-all hover:from-sky-600 hover:to-sky-700 active:scale-[0.99]"
                  >
                    <Send className="h-4.5 w-4.5" />
                    <span className="text-sm font-medium">Send</span>
                    <ArrowRight className="h-4 w-4 opacity-80 transition-transform group-hover/btn:translate-x-0.5" />
                  </Link>

                  <Link
                    href="/generate"
                    className="group/btn inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-emerald-600 text-white shadow-lg transition-all hover:from-emerald-600 hover:to-emerald-700 active:scale-[0.99]"
                  >
                    <QrCode className="h-4.5 w-4.5" />
                    <span className="text-sm font-medium">Receive</span>
                    <ArrowRight className="h-4 w-4 opacity-80 transition-transform group-hover/btn:translate-x-0.5" />
                  </Link>
                </div>

                {/* 说明条 */}
                <div className="mt-4 w-full max-w-[260px] rounded-xl border border-slate-200 bg-white/70 p-3 text-center text-[12.5px] text-slate-600 shadow-sm">
                  <span className="font-medium text-slate-700">Flow:</span> scan code → one-time address →
                  on-chain signal/announce → MPC 2/3 discover
                </div>
              </div>
            </div>

            {/* 边缘高光 */}
            <div className="pointer-events-none absolute -inset-[2px] rounded-[28px] bg-gradient-to-br from-white/0 via-white/40 to-white/0 opacity-0 blur-xl transition-opacity duration-500 group-hover:opacity-100" />
          </div>
        </section>

        {/* 页脚小字 */}
        <footer className="mt-12 text-center text-xs text-slate-500">
          Non-custodial • Minimal on-chain footprint • Optional audit via Announce
        </footer>
      </div>
    </main>
  );
}
