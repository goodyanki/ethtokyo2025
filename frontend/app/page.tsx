import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-white to-[#f7f9fc] text-[#0f172a]">
      <div className="mx-auto max-w-5xl px-6 py-16">
        <header className="mb-12">
          <h1 className="text-4xl font-semibold tracking-tight">demo</h1>
          <p className="mt-2 text-sm text-[#475569]">web3 · privacy · zk</p>
        </header>

        <section className="flex items-center justify-center">
          <div className="relative w-[320px] h-[520px] rounded-3xl border border-[#e2e8f0] bg-white/90 shadow-[0_12px_40px_rgba(15,23,42,0.08)] backdrop-blur-sm">
            <div className="absolute inset-0 rounded-3xl pointer-events-none" style={{ background: "radial-gradient(120% 60% at 50% -20%, rgba(99,102,241,0.10) 0%, rgba(59,130,246,0.08) 35%, transparent 70%)" }} />
            <div className="relative h-full flex flex-col items-center justify-center gap-6 p-8">
              <div className="text-lg font-medium text-[#0f172a]">NomadPay</div>
              <div className="text-[13px] text-[#64748b]">Stealth + ZK · Light Theme</div>
              <div className="mt-4 flex flex-col gap-4 w-full max-w-[220px]">
                <Link href="/send" className="inline-flex items-center justify-center rounded-xl h-11 bg-[#0ea5e9] text-white hover:bg-[#0284c7] transition-colors">Send</Link>
                <Link href="/generate" className="inline-flex items-center justify-center rounded-xl h-11 bg-[#10b981] text-white hover:bg-[#059669] transition-colors">Receive</Link>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
