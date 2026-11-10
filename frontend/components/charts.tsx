"use client";

import { type KeyboardEvent, useEffect, useRef, useState } from "react";

const MAX_SCORE = 5;
const TICKS = [1, 2, 3, 4, 5];

// ---- Criterion scores: horizontal bars ----------------------------------------------------

export type Bar = { label: string; score: number };

/** One bar per criterion, 0 to 5, the value printed at the tip. Bars are single series, so
 * there's no legend: the section title says what's plotted. The cards below the chart repeat
 * every score in text, which is the table view. */
export function ScoreBars({ bars }: { bars: Bar[] }) {
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <figure className="space-y-1">
      <div className="relative">
        {bars.map((bar, index) => (
          <div
            key={bar.label}
            className="grid grid-cols-[8.5rem_1fr] items-center gap-3 py-1.5"
          >
            <span className="truncate text-sm text-muted">{bar.label}</span>
            <div
              tabIndex={0}
              role="img"
              aria-label={`${bar.label}: ${bar.score} out of ${MAX_SCORE}`}
              onPointerEnter={() => setHovered(index)}
              onPointerLeave={() => setHovered(null)}
              onFocus={() => setHovered(index)}
              onBlur={() => setHovered(null)}
              className="relative h-7 rounded outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <Gridlines />
              <div
                className="absolute inset-y-0 left-0 my-auto h-5 rounded-r bg-accent transition-[filter]"
                style={{
                  width: `${(bar.score / MAX_SCORE) * 100}%`,
                  filter: hovered === index ? "brightness(1.12)" : undefined,
                }}
              />
              <span
                className="absolute inset-y-0 flex items-center pl-2 text-sm font-semibold tabular-nums"
                style={{ left: `${(bar.score / MAX_SCORE) * 100}%` }}
              >
                {bar.score}
              </span>
            </div>
          </div>
        ))}
      </div>
      {/* The axis: the same positions as the gridlines. */}
      <div className="grid grid-cols-[8.5rem_1fr] gap-3">
        <span />
        <div className="relative h-4 text-xs tabular-nums text-muted">
          {[0, ...TICKS].map((tick) => (
            <span
              key={tick}
              className="absolute -translate-x-1/2"
              style={{ left: `${(tick / MAX_SCORE) * 100}%` }}
            >
              {tick}
            </span>
          ))}
        </div>
      </div>
    </figure>
  );
}

function Gridlines() {
  return (
    <div aria-hidden className="absolute inset-0">
      {TICKS.map((tick) => (
        <span
          key={tick}
          className="absolute inset-y-0 w-px bg-[var(--chart-grid)]"
          style={{ left: `${(tick / MAX_SCORE) * 100}%` }}
        />
      ))}
    </div>
  );
}

// ---- Overall score over time: a line ------------------------------------------------------

export type Point = { date: string; score: number; label: string };

const HEIGHT = 180;
const PAD = { top: 16, right: 36, bottom: 26, left: 28 };

/** Overall score per finished interview, oldest to newest. A crosshair snaps to the nearest
 * interview on hover, and the arrow keys move it when the chart has focus. */
export function ProgressChart({ points }: { points: Point[] }) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [active, setActive] = useState<number | null>(null);

  // Draw at the real width, so text and lines keep their size (a stretched SVG would squash them).
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(240, entry.contentRect.width)),
    );
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  const plotW = width - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const x = (i: number) =>
    PAD.left +
    (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const y = (score: number) =>
    PAD.top + plotH - ((score - 1) / (MAX_SCORE - 1)) * plotH;

  const line = points
    .map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.score)}`)
    .join(" ");
  const area = `${line} L${x(points.length - 1)},${y(1)} L${x(0)},${y(1)} Z`;
  const last = points.length - 1;

  function nearest(clientX: number) {
    const box = boxRef.current?.getBoundingClientRect();
    if (!box || points.length === 0) return;
    const fraction = (clientX - box.left - PAD.left) / plotW;
    setActive(Math.min(last, Math.max(0, Math.round(fraction * last))));
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const step = event.key === "ArrowRight" ? 1 : -1;
    setActive((current) =>
      Math.min(last, Math.max(0, (current ?? last) + step)),
    );
  }

  const shown = active === null ? null : points[active];

  return (
    <figure className="space-y-2">
      <div
        ref={boxRef}
        tabIndex={0}
        role="img"
        aria-label={`Overall score over ${points.length} interviews, from ${points[0].score.toFixed(1)} to ${points[last].score.toFixed(1)}. Use the arrow keys to read each one.`}
        onPointerMove={(e) => nearest(e.clientX)}
        onPointerLeave={() => setActive(null)}
        onFocus={() => setActive(last)}
        onBlur={() => setActive(null)}
        onKeyDown={onKeyDown}
        className="relative touch-pan-y rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <svg width={width} height={HEIGHT} className="block">
          {TICKS.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke="var(--chart-grid)"
                strokeWidth={1}
              />
              <text
                x={PAD.left - 10}
                y={y(tick)}
                textAnchor="end"
                dominantBaseline="middle"
                className="fill-[var(--muted)] text-[11px] tabular-nums"
              >
                {tick}
              </text>
            </g>
          ))}
          <path d={area} fill="var(--accent)" opacity={0.1} />
          <path
            d={line}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {shown && active !== null && (
            <line
              x1={x(active)}
              x2={x(active)}
              y1={PAD.top}
              y2={y(1)}
              stroke="var(--muted)"
              strokeWidth={1}
            />
          )}
          {/* The newest result, labelled; the hovered one gets the same marker. */}
          {[last, ...(active !== null && active !== last ? [active] : [])].map(
            (i) => (
              <circle
                key={i}
                cx={x(i)}
                cy={y(points[i].score)}
                r={4.5}
                fill="var(--accent)"
                stroke="var(--surface)"
                strokeWidth={2}
              />
            ),
          )}
          <text
            x={x(last) + 9}
            y={y(points[last].score)}
            dominantBaseline="middle"
            className="fill-[var(--foreground)] text-xs font-semibold tabular-nums"
          >
            {points[last].score.toFixed(1)}
          </text>
          <text
            x={PAD.left}
            y={HEIGHT - 6}
            className="fill-[var(--muted)] text-[11px]"
          >
            {shortDate(points[0].date)}
          </text>
          {points.length > 1 && (
            <text
              x={width - PAD.right}
              y={HEIGHT - 6}
              textAnchor="end"
              className="fill-[var(--muted)] text-[11px]"
            >
              {shortDate(points[last].date)}
            </text>
          )}
        </svg>

        {shown && active !== null && (
          <div
            className="pointer-events-none absolute top-1 z-10 w-max max-w-56 -translate-x-1/2 rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-md"
            style={{ left: Math.min(Math.max(x(active), 70), width - 70) }}
          >
            <p className="text-base font-semibold tabular-nums">
              {shown.score.toFixed(1)}
              <span className="text-xs font-normal text-muted"> / 5</span>
            </p>
            <p className="truncate">{shown.label}</p>
            <p className="text-muted">{shortDate(shown.date)}</p>
          </div>
        )}
      </div>

      <details className="text-sm">
        <summary className="cursor-pointer text-muted hover:text-foreground">
          Show as a table
        </summary>
        <table className="mt-2 w-full text-left">
          <thead className="text-muted">
            <tr>
              <th className="py-1 font-medium">Date</th>
              <th className="py-1 font-medium">Interview</th>
              <th className="py-1 text-right font-medium">Score</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            {points.map((p, i) => (
              <tr key={i} className="border-t border-line">
                <td className="py-1">{shortDate(p.date)}</td>
                <td className="py-1">{p.label}</td>
                <td className="py-1 text-right">{p.score.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}
