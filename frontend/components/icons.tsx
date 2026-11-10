import { useId } from "react";

// Small line icons, drawn inline so there's no icon library to load. They take the text colour
// (stroke="currentColor") and are hidden from screen readers: the button or link around them
// carries the accessible name.

type IconProps = { className?: string };

function Icon({
  className = "h-5 w-5",
  children,
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      {children}
    </svg>
  );
}

export const PlusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);

export const MenuIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Icon>
);

export const CloseIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Icon>
);

export const MicIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </Icon>
);

export const SendIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 19V5M6 11l6-6 6 6" />
  </Icon>
);

export const SpeakerIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 10v4h4l5 4V6L8 10H4z" />
    <path d="M16.5 9a4 4 0 0 1 0 6M19 6.5a7.5 7.5 0 0 1 0 11" />
  </Icon>
);

export const LogoutIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10" />
  </Icon>
);

export const ReportIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
  </Icon>
);

export const CheckIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12.5l4.5 4.5L19 7" />
  </Icon>
);

export const ArrowUpRightIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 17L17 7M9 7h8v8" />
  </Icon>
);

export const BugIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="7" y="7" width="10" height="13" rx="5" />
    <path d="M9 7.5a3 3 0 0 1 6 0M12 11v9M7 12H3M21 12h-4M7.5 16.5L4 19M16.5 16.5L20 19M7.5 8.5L4.5 6M16.5 8.5l3-2.5" />
  </Icon>
);

/** The Offerward mark, "O›": the O of Offerward, then a step forward. The same drawing as
 * app/icon.svg (the browser tab icon). */
export function Logo({ className = "h-7 w-7" }: IconProps) {
  // Each logo on the page needs its own gradient id: ids must be unique in a document.
  const gradient = useId();
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={className}>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b8ff0" />
          <stop offset="1" stopColor="#1d4fb0" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill={`url(#${gradient})`} />
      <g
        fill="none"
        stroke="#fff"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <circle cx="13" cy="16" r="6" />
        <path d="M21 10.5L26 16L21 21.5" />
      </g>
    </svg>
  );
}
