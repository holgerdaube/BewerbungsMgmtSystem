/** @type {import('tailwindcss').Config} */

// P2-72 (Design aus einer Quelle): Die Markenwerte stehen NICHT mehr in dieser Datei. Das Backend
// liefert sie zur Laufzeit als CSS-Variablen (GET /api/design.css, Quelle: assets/design/standard.json
// bzw. die Überschreibung unter data/design/). Tailwind rechnet hier nur noch `rgb(var(--…) / Deckkraft)`
// ein; alle Klassennamen (`bg-brand-cyan`, `text-brand-navy/60`, `border-brand-cyan/40`, `slate-…`)
// bleiben gültig, auch die mit Deckkraft. Es gibt bewusst KEINEN Rückfallwert in `var(…, …)`: Eine
// zweite Stelle mit Farbwerten wäre eine zweite Quelle.
// Die Kanäle heißen wie die Rollen der Design-Datei (pipeline/design.py, `variablenname`).
const rolle = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Daube.Tech brand — die Klassennamen bleiben, die Werte kommen aus der Rolle.
        brand: {
          navy: rolle('marke'),
          cyan: rolle('aktion'),
          cyanHover: rolle('aktion-hover'),
          steel: rolle('stahl'),
          // Schrift auf den Flächen: `aufAktion` (weiß in der Vorgabe) auf Aktionsflächen,
          // `aufMarke` auf der Markenfläche (Seitenleiste).
          aufAktion: rolle('auf-aktion'),
          aufMarke: rolle('auf-marke'),
        },
        // Phase 80 (Styleguide v5 §18.2 UI-Neutrals): nur diese vier Stufen überschreiben —
        // Tailwind merged per Stufe, 300/400/600/700 bleiben Default.
        // P2-72: Die vier Stufen folgen den Rollen flaeche (100), rahmen (200), text_gedaempft (500)
        // und text (800).
        slate: {
          100: rolle('flaeche'),
          200: rolle('rahmen'),
          500: rolle('text-gedaempft'),
          800: rolle('text'),
        },
      },
      // P2-72: Die vollständigen Schriftstapel liefert das Backend (--schrift-text,
      // --schrift-ueberschrift); eigene Schriftdateien eines Partners gibt es in diesem Schritt nicht.
      fontFamily: {
        sans: ['var(--schrift-text)'],
        heading: ['var(--schrift-ueberschrift)'],
      },
    },
  },
  plugins: [],
}
