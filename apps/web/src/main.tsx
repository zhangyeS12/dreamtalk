import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { discoverConnection, recoverConnection, acknowledgeReady } from "./connection";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><App discover={discoverConnection} recover={recoverConnection} onReady={acknowledgeReady} /></StrictMode>,
);
