import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

document.title = import.meta.env.VITE_PORTAL === "storefront"
  ? "星云商城 | 智能购物与售后"
  : "SmartSupport | 企业级智能客服系统";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
