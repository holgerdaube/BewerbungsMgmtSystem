import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
// Phase 80 (§5): Inter (Body) + Montserrat (Headlines) self-hosted laden — vor dem
// CSS-Import, damit die @font-face-Regeln vor den ersten Utility-Klassen registriert sind.
import '@fontsource/inter/400.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/montserrat/600.css'
import '@fontsource/montserrat/700.css'
import '@fontsource/montserrat/800.css'
import './index.css'
import { i18nStarten } from './i18n'

// P2-88: Die Sprache steht fest, bevor die App geladen wird. So zeigt die Seite nie kurz die falsche
// Sprache, und Texte außerhalb von Komponenten stimmen ebenfalls. i18nStarten wirft nie.
i18nStarten()
  .then(() => import('./App'))
  .then(({ default: App }) => {
    ReactDOM.createRoot(document.getElementById('root')!).render(
      <React.StrictMode>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </React.StrictMode>,
    )
  })
