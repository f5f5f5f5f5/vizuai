import { createRoot, hydrateRoot } from "react-dom/client";
import App from "./app/App.tsx";
import "./styles/index.css";

const rootElement = document.getElementById("root")!;

if (rootElement.hasChildNodes()) {
  hydrateRoot(rootElement, <App />);
} else {
  createRoot(rootElement).render(<App />);
}
