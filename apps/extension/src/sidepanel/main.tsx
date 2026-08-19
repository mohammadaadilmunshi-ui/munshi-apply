import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import "./form-controls.css";
import "./resume-vault.css";
// Owner-facing design layers intentionally load last so they can refine every screen consistently.
import "./ux-overhaul.css";
import "./ux-polish.css";

const root = document.getElementById("root");
if (!root) throw new Error("Side panel root not found");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
