// src/main.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
// Fonts ship with the app (OFL): no request to a font CDN, which told Google
// every time BitcoinTX opened. Latin and Latin Extended only; other scripts
// fall back to the system font.
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-ext-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-ext-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/inter/latin-ext-600.css";
import "@fontsource/inter/latin-700.css";
import "@fontsource/inter/latin-ext-700.css";
import "@fontsource/outfit/latin-500.css";
import "@fontsource/outfit/latin-ext-500.css";
import "@fontsource/outfit/latin-600.css";
import "@fontsource/outfit/latin-ext-600.css";
import "@fontsource/outfit/latin-700.css";
import "@fontsource/outfit/latin-ext-700.css";
// Styles first, so the page stylesheets App pulls in come after the shared
// ones and only have to lay them out.
import './styles/index.css'; // Minimal resets
import './styles/theme.css'; // Design tokens
import './styles/components.css'; // Shared buttons, inputs, cards
import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);