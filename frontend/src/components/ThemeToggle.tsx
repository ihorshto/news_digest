import { t } from "../i18n/uk";
import { nextTheme, useTheme, type ThemeChoice } from "../lib/theme";

const labels: Record<ThemeChoice, string> = {
  system: t.nav.themeSystem,
  light: t.nav.themeLight,
  dark: t.nav.themeDark,
};

function Icon({ choice }: { choice: ThemeChoice }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  if (choice === "light")
    return (
      <svg {...common} aria-hidden>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    );
  if (choice === "dark")
    return (
      <svg {...common} aria-hidden>
        <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
      </svg>
    );
  return (
    <svg {...common} aria-hidden>
      <rect x="3" y="4" width="18" height="13" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}

export function ThemeToggle() {
  const [choice, setChoice] = useTheme();
  return (
    <button
      type="button"
      onClick={() => setChoice(nextTheme(choice))}
      className="inline-flex h-8 items-center gap-2 rounded-lg px-2.5 text-[13px] text-muted transition-colors hover:bg-surface-2 hover:text-text"
      title={labels[choice]}
      aria-label={labels[choice]}
    >
      <Icon choice={choice} />
      <span className="hidden sm:inline">{labels[choice]}</span>
    </button>
  );
}
