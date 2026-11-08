/**
 * DocuMind AI design tokens, following the cottagehomecare.com visual identity:
 * deep navy primary (#1C3461), warm orange accent (#E57824), cool light-gray canvas (#F1F4F8),
 * warm cream sections (#FDF9F3), Plus Jakarta Sans headings + Inter body, pill buttons, rounded-2xl cards.
 * Values marked (ref) were taken directly from the reference site's CSS.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // primary: navy
        brand: {
          50: "#EEF2FB", // (ref)
          100: "#DFE8F5", // (ref)
          200: "#C3D2EA",
          300: "#94ACD4",
          400: "#5B7FBE",
          500: "#2F5FB0", // (ref)
          600: "#26508F",
          700: "#1A365D", // (ref)
          800: "#1C3461", // (ref) primary
          900: "#13254A",
          950: "#0B1120", // (ref)
        },
        // accent: orange (calls to action, highlights)
        accent: {
          50: "#FFF6EC", // (ref)
          100: "#FDE9D5",
          200: "#F9CFA6",
          300: "#F4AE6E",
          400: "#F28C28", // (ref)
          500: "#E57824", // (ref) accent
          600: "#CF6A1C",
          700: "#A9531A",
        },
        cream: { DEFAULT: "#F1F4F8", dark: "#E8EEF6" }, // (ref) app canvas / hover
        sand: { DEFAULT: "#FDF9F3", dark: "#F5F3F0" }, // (ref) warm section backgrounds
        ink: { DEFAULT: "#1A1C21", soft: "#334155" }, // (ref) heading / slate-700 body
        muted: "#64748B", // slate-500
        line: "#E2E8F0", // slate-200
        ok: { DEFAULT: "#059669", bg: "#E6F6EF" }, // emerald-600 (ref)
        warn: { DEFAULT: "#B45309", bg: "#FEF3DF" }, // amber (distinct from the orange accent)
        bad: { DEFAULT: "#DC2626", bg: "#FDECEC" },
        info: { DEFAULT: "#2F5FB0", bg: "#EEF2FB" },
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', "Inter", "system-ui", "sans-serif"],
        sans: ['"Inter"', "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        hand: ['"Caveat Brush"', "cursive"],
      },
      borderRadius: { xl: "12px", "2xl": "16px", "3xl": "24px" },
      boxShadow: {
        soft: "0 4px 20px rgba(0,0,0,0.03)", // (ref)
        lift: "0 12px 32px -10px rgba(15,23,42,0.28)", // (ref)
        navy: "0 20px 50px -12px rgba(26,54,93,0.35)", // (ref)
        cta: "0 6px 18px -4px rgba(229,120,36,0.45)",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(90deg, #1C3461, #E57824)", // (ref) progress bars
        "navy-panel": "linear-gradient(135deg, #1C3461 0%, #1A365D 55%, #13254A 100%)",
      },
      keyframes: {
        "fade-in": { from: { opacity: 0, transform: "translateY(4px)" }, to: { opacity: 1, transform: "none" } },
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
      },
      animation: { "fade-in": "fade-in .25s ease-out both", shimmer: "shimmer 1.4s linear infinite" },
    },
  },
  plugins: [],
};
