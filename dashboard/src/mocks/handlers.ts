import { http, HttpResponse } from "msw";
import type { Health } from "@/api/types";

const health: Health = {
  status: "ok",
  app_version: "0.1.0-mock",
  code_hash: "mock".padEnd(64, "0"),
  config_hash: "mock".padEnd(64, "0"),
  db_path: ":memory:",
  active_models: {},
};

// Populated screen by screen; see mocks/generate.ts once the fixture generator lands.
export const handlers = [http.get("/api/v1/health", () => HttpResponse.json(health))];
