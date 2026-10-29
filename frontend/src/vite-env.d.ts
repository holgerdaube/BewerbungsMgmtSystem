/// <reference types="vite/client" />
// Phase 71E: bislang gab es diese Datei nicht — `tsc --noEmit` kannte Vites eigene
// Modul-Deklarationen (u. a. `*?raw` für die Rechtliches-Seite, s. pages/Rechtliches.tsx)
// dadurch nicht, obwohl `vite build` selbst `?raw`-Imports längst nativ unterstützt.
