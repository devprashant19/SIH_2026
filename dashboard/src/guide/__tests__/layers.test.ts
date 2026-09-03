import { afterEach, describe, expect, it, vi } from "vitest";
import { isTopLayer, layerDepth, popLayer, pushLayer, resetLayers } from "../layers";

/** Stands in for the Drawer, which registers on document in the bubble phase. */
function drawerListener(spy: () => void) {
  const handler = (e: KeyboardEvent) => {
    if (e.key === "Escape") spy();
  };
  document.addEventListener("keydown", handler);
  return () => document.removeEventListener("keydown", handler);
}

function pressEscape() {
  document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
}

afterEach(() => resetLayers());

describe("escape layer stack", () => {
  it("leaves the drawer alone when no guide layer is pushed", () => {
    const drawer = vi.fn();
    const off = drawerListener(drawer);
    pressEscape();
    expect(drawer).toHaveBeenCalledTimes(1);
    off();
  });

  it("stops the event reaching the drawer while a guide layer is on top", () => {
    const drawer = vi.fn();
    const guide = vi.fn();
    const off = drawerListener(drawer);
    const id = pushLayer(guide);

    pressEscape();
    expect(guide).toHaveBeenCalledTimes(1);
    expect(drawer).not.toHaveBeenCalled();

    popLayer(id);
    pressEscape();
    expect(guide).toHaveBeenCalledTimes(1);
    expect(drawer).toHaveBeenCalledTimes(1);
    off();
  });

  it("dismisses the topmost layer only", () => {
    const lower = vi.fn();
    const upper = vi.fn();
    const a = pushLayer(lower);
    const b = pushLayer(upper);

    expect(isTopLayer(b)).toBe(true);
    expect(isTopLayer(a)).toBe(false);
    expect(layerDepth()).toBe(2);

    pressEscape();
    expect(upper).toHaveBeenCalledTimes(1);
    expect(lower).not.toHaveBeenCalled();

    popLayer(b);
    pressEscape();
    expect(lower).toHaveBeenCalledTimes(1);
    popLayer(a);
  });
});
