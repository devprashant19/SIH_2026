import { describe, expect, it } from "vitest";
import { place, type Rect } from "../usePlacement";

const VIEWPORT = { w: 1000, h: 800 };
const POP = { w: 360, h: 200 };

const rect = (top: number, left: number, w = 100, h = 40): Rect => ({
  top,
  left,
  width: w,
  height: h,
  right: left + w,
  bottom: top + h,
});

describe("popover placement", () => {
  it("prefers below the target when there is room", () => {
    const p = place(rect(100, 400), POP, VIEWPORT);
    expect(p.side).toBe("bottom");
    expect(p.top).toBe(150); // 100 + 40 + gap
  });

  it("flips above when the target is near the bottom", () => {
    const p = place(rect(740, 400), POP, VIEWPORT);
    expect(p.side).toBe("top");
    expect(p.top).toBe(530); // 740 - gap - 200
  });

  it("clamps inside the left edge and keeps the arrow on the target", () => {
    const p = place(rect(100, 4, 40), POP, VIEWPORT);
    expect(p.left).toBe(12);
    // Target centre is x = 24, which is 12px into a popover placed at x = 12. The arrow is
    // held 14px clear of the corner so it never sits on the radius.
    expect(p.arrow).toBe(14);
  });

  it("clamps inside the right edge", () => {
    const p = place(rect(100, 960, 40), POP, VIEWPORT);
    expect(p.left).toBe(VIEWPORT.w - POP.w - 12);
  });

  it("falls back to the side with the least deficit when nothing fits", () => {
    const tall = { w: 360, h: 900 };
    const p = place(rect(400, 400), tall, VIEWPORT);
    expect(["top", "bottom", "left", "right"]).toContain(p.side);
    expect(p.top).toBeGreaterThanOrEqual(12);
  });

  it("honours an explicit side preference", () => {
    const p = place(rect(300, 400), POP, VIEWPORT, ["right"]);
    expect(p.side).toBe("right");
    expect(p.left).toBe(510); // 400 + 100 + gap
  });
});
