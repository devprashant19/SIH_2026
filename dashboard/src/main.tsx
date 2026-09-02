import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { Providers } from "./app/providers";
import { router } from "./app/router";
import "./styles/globals.css";

async function bootstrap() {
  // Mock Service Worker lets the UI be developed before the API exists (VITE_MOCK=1).
  if (import.meta.env.VITE_MOCK === "1") {
    const { startMocks } = await import("./mocks/browser");
    await startMocks();
  }
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <Providers>
        <RouterProvider router={router} />
      </Providers>
    </React.StrictMode>,
  );
}

void bootstrap();
