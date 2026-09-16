import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { discoverConnection, acknowledgeReady } from "./connection";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><App discover={discoverConnection} onReady={acknowledgeReady} /></StrictMode>,
);
