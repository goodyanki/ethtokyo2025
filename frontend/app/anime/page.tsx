"use client";

import React, { useMemo, useRef, useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";

/**
 * Next.js (App Router) page.tsx
 * - Two avatars left/right with subtle idle animation (对波感)
 * - Click left avatar -> modal with "Send" button -> shoots a laser to the right
 * - Click right avatar -> modal with "Generate" button -> spawns a black-hole animation
 * - Floating QR container pinned to the top center
 *
 * Styling: TailwindCSS (recommended). Animations: Framer Motion.
 *
 * Replace QR_URL with your QR image URL or <img src="..."/> contents.
 * Replace LEFT_FRAMES / RIGHT_FRAMES with your two-frame sprites.
 */

// Use existing public assets to avoid missing files in dev
const QR_URL = "/globe.svg";
const LEFT_FRAMES = ["/file.svg", "/window.svg"];
const RIGHT_FRAMES = ["/next.svg", "/vercel.svg"];

export default function Page() {
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  // Laser shots are ephemeral; each id renders one beam animation then removes itself
  const [shots, setShots] = useState<number[]>([]);
  const shotId = useRef(0);

  // Black hole visibility
  const [blackHole, setBlackHole] = useState(false);

  // Optional: auto-hide black hole after a short time
  useEffect(() => {
    if (blackHole) {
      const t = setTimeout(() => setBlackHole(false), 2800);
      return () => clearTimeout(t);
    }
  }, [blackHole]);

  const addShot = () => {
    const id = ++shotId.current;
    setShots(prev => prev.concat(id));
    // Remove this shot after animation ends
    setTimeout(() => {
      setShots(prev => prev.filter(s => s !== id));
    }, 900);
  };

  return (
    <main className="relative min-h-screen overflow-hidden bg-gradient-to-b from-white to-slate-50 text-slate-900">
      {/* Floating QR container */}
      <div className="pointer-events-auto fixed left-1/2 top-3 z-50 -translate-x-1/2">
        <div className="flex items-center gap-3 rounded-2xl bg-white/80 p-3 shadow-xl ring-1 ring-slate-200 backdrop-blur">
          <div className="text-sm font-medium">Scan me</div>
          <div className="h-14 w-14 overflow-hidden rounded-lg ring-1 ring-slate-200">
            {/* Replace with your QR element */}
            <img src={QR_URL} alt="QR Code" className="h-full w-full object-cover" />
          </div>
        </div>
      </div>

      {/* Scene container */}
      <section className="relative mx-auto mt-28 grid max-w-6xl grid-cols-1 gap-10 px-6 pb-24 md:grid-cols-2">
        {/* LEFT ACTOR */}
        <div className="relative flex items-center justify-center">
          <Actor
            facing="right"
            label="Sender"
            onClick={() => setLeftOpen(true)}
            color="indigo"
            frameA={LEFT_FRAMES[0]}
            frameB={LEFT_FRAMES[1]}
            width={180}
            height={180}
          />
        </div>

        {/* RIGHT ACTOR */}
        <div className="relative flex items-center justify-center">
          <Actor
            facing="left"
            label="Receiver"
            onClick={() => setRightOpen(true)}
            color="rose"
            frameA={RIGHT_FRAMES[0]}
            frameB={RIGHT_FRAMES[1]}
            width={180}
            height={180}
          />
        </div>

        {/* Idle conversational waves (对波氛围) */}
        <Waves side="left" />
        <Waves side="right" />

        {/* Laser beams */}
        <AnimatePresence>
          {shots.map(id => (
            <Laser key={id} />
          ))}
        </AnimatePresence>

        {/* Black hole */}
        <BlackHole visible={blackHole} />
      </section>

      {/* Modals */}
      <Modal open={leftOpen} onClose={() => setLeftOpen(false)} title="Send a beam">
        <p className="text-sm text-slate-600">Click send to fire a laser to the other side.</p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            className="rounded-xl bg-slate-100 px-4 py-2 text-slate-700 ring-1 ring-inset ring-slate-200 hover:bg-slate-200"
            onClick={() => setLeftOpen(false)}
          >
            Cancel
          </button>
          <button
            className="rounded-xl bg-indigo-600 px-4 py-2 font-semibold text-white shadow hover:bg-indigo-500"
            onClick={() => {
              setLeftOpen(false);
              addShot();
            }}
          >
            Send
          </button>
        </div>
      </Modal>

      <Modal open={rightOpen} onClose={() => setRightOpen(false)} title="Generate a black hole">
        <p className="text-sm text-slate-600">Click generate to spawn a swirling black hole.</p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            className="rounded-xl bg-slate-100 px-4 py-2 text-slate-700 ring-1 ring-inset ring-slate-200 hover:bg-slate-200"
            onClick={() => setRightOpen(false)}
          >
            Cancel
          </button>
          <button
            className="rounded-xl bg-rose-600 px-4 py-2 font-semibold text-white shadow hover:bg-rose-500"
            onClick={() => {
              setRightOpen(false);
              setBlackHole(true);
            }}
          >
            Generate
          </button>
        </div>
      </Modal>
    </main>
  );
}

// ——————————————————————————————————————————————————————————
// Components
// ——————————————————————————————————————————————————————————

function TwoFrameSprite({ a, b, w, h }: { a: string; b: string; w: number; h: number }) {
  const [onA, setOnA] = useState(true);
  useEffect(() => {
    const t = setInterval(() => setOnA(v => !v), 140); // ~7fps toggle
    return () => clearInterval(t);
  }, []);
  return (
    <img
      src={onA ? a : b}
      width={w}
      height={h}
      alt="sprite"
      draggable={false}
      className="select-none drop-shadow-[0_8px_20px_rgba(2,6,23,0.15)]"
    />
  );
}

function Actor({
  facing,
  label,
  onClick,
  color = "indigo",
  frameA,
  frameB,
  width = 180,
  height = 180,
}: {
  facing: "left" | "right";
  label: string;
  onClick: () => void;
  color?: "indigo" | "rose" | "emerald" | "violet";
  frameA: string;
  frameB: string;
  width?: number;
  height?: number;
}) {
  const flip = useMemo(() => (facing === "left" ? "scale-x-[-1]" : ""), [facing]);
  const hue = useMemo(() => {
    if (color === "rose") return "from-rose-400 to-rose-600";
    if (color === "emerald") return "from-emerald-400 to-emerald-600";
    if (color === "violet") return "from-violet-400 to-violet-600";
    return "from-indigo-400 to-indigo-600";
  }, [color]);

  return (
    <motion.button
      onClick={onClick}
      className="group relative select-none rounded-3xl p-4 outline-none"
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.98 }}
    >
      {/* Glow */}
      <div className={`pointer-events-none absolute -inset-6 rounded-[2rem] bg-gradient-to-br ${hue} opacity-20 blur-2xl`} />

      {/* Avatar (two-frame sprite with gentle bobbing) */}
      <motion.div
        className={`relative z-10 ${flip}`}
        animate={{ y: [0, -6, 0] }}
        transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
      >
        <TwoFrameSprite a={frameA} b={frameB} w={width} h={height} />
      </motion.div>

      {/* Label */}
      <div className="relative z-10 mt-2 text-center text-sm font-semibold text-slate-700">
        {label}
      </div>
    </motion.button>
  );
}

function Waves({ side }: { side: "left" | "right" }) {
  // Decorative radio-wave ripples near each actor to give 对波感
  const common = "pointer-events-none absolute top-1/2 h-24 w-24 -translate-y-1/2";
  const pos = side === "left" ? "left-[22%]" : "right-[22%]";
  return (
    <div className={`${common} ${pos}`}>
      <motion.div
        className="absolute inset-0 rounded-full ring-2 ring-indigo-400/40"
        animate={{ scale: [1, 1.2, 1], opacity: [0.6, 0.2, 0.6] }}
        transition={{ duration: 2.6, repeat: Infinity, ease: "easeInOut", delay: side === "left" ? 0 : 0.8 }}
      />
      <motion.div
        className="absolute inset-0 rounded-full ring-2 ring-rose-400/40"
        animate={{ scale: [0.7, 1.1, 0.7], opacity: [0.5, 0.15, 0.5] }}
        transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut", delay: side === "left" ? 0.6 : 0 }}
      />
    </div>
  );
}

function Laser() {
  // A horizontal beam that grows from 15% to 85% of scene width
  return (
    <>
      <motion.div
        className="pointer-events-none absolute left-[15%] top-[56%] z-30 h-1 origin-left rounded-full bg-gradient-to-r from-fuchsia-500 via-pink-500 to-violet-500 shadow-[0_0_20px_rgba(217,70,239,0.9)]"
        initial={{ width: 0, opacity: 0.9 }}
        animate={{ width: "70%", opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      />
      {/* Impact flash */}
      <motion.div
        className="pointer-events-none absolute left-[85%] top-[56%] z-30 h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full bg-violet-400 blur-sm"
        initial={{ scale: 0, opacity: 0.0 }}
        animate={{ scale: [0, 1.6, 0.8], opacity: [0, 1, 0] }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      />
    </>
  );
}

function BlackHole({ visible }: { visible: boolean }) {
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="pointer-events-none absolute right-[18%] top-[58%] z-20 -translate-y-1/2"
          initial={{ scale: 0.2, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.2, opacity: 0 }}
          transition={{ type: "spring", stiffness: 220, damping: 18 }}
        >
          <div className="relative h-44 w-44">
            {/* Accretion disk */}
            <motion.div
              className="absolute inset-0 rounded-full"
              style={{
                background:
                  "conic-gradient(from 0deg at 50% 50%, rgba(244,63,94,0.0), rgba(244,63,94,0.35), rgba(99,102,241,0.35), rgba(244,63,94,0.0))",
                filter: "blur(2px)",
              }}
              animate={{ rotate: 360 }}
              transition={{ duration: 3.2, repeat: Infinity, ease: "linear" }}
            />
            {/* Event horizon */}
            <div className="absolute inset-[18%] rounded-full bg-black shadow-[inset_0_0_40px_rgba(0,0,0,0.8)]" />
            {/* Gravitational lens glow */}
            <motion.div
              className="absolute inset-[6%] rounded-full ring-4 ring-white/10"
              animate={{ scale: [1, 1.05, 1] }}
              transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
            />
            {/* Stars */}
            <Stars />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Stars() {
  // Sprinkle a few twinkling dots
  const dots = [
    { top: "10%", left: "8%" },
    { top: "22%", left: "78%" },
    { top: "72%", left: "66%" },
    { top: "60%", left: "12%" },
    { top: "36%", left: "44%" },
  ];
  return (
    <>
      {dots.map((d, i) => (
        <motion.span
          key={i}
          className="absolute h-1.5 w-1.5 rounded-full bg-white/80"
          style={{ top: d.top as string, left: d.left as string }}
          animate={{ opacity: [0.2, 1, 0.2], scale: [0.8, 1.2, 0.8] }}
          transition={{ duration: 1.8 + i * 0.2, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
    </>
  );
}

function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            className="fixed left-1/2 top-1/2 z-50 w-[92%] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white p-6 shadow-2xl ring-1 ring-slate-200"
            initial={{ y: 30, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 20, opacity: 0, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 320, damping: 24 }}
          >
            <div className="mb-2 text-lg font-semibold text-slate-900">{title}</div>
            <div className="text-slate-700">{children}</div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
