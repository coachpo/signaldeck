import "./display-handoff";

  import { createRoot } from "react-dom/client";
  import App from "./App.tsx";
  import { watchChunkLoadFailures } from "./lib/chunk-recovery";
  import { router } from "./routes";
  import "./styles/index.css";

  watchChunkLoadFailures(router);
  createRoot(document.getElementById("root")!).render(<App />);
  
