import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { ROUTE_PATHS } from "@/app/router";
import { NAV_ITEMS } from "@/app/router";
import { EXEMPT_CONTROLS } from "../exempt";
import { anchorOf } from "../model";
import { ALL_ANCHORS, assertModelIntegrity, BY_ANCHOR, ROUTE_SCREENS, SCREENS } from "../registry";
import { TOURS } from "../tours";

const SRC = join(process.cwd(), "src");

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === "__tests__" || name === "mocks") continue;
      walk(full, out);
    } else if (name.endsWith(".tsx") || name.endsWith(".ts")) {
      out.push(full);
    }
  }
  return out;
}

interface Found {
  anchor: string;
  file: string;
  line: number;
}

interface Interactive {
  symbol: string;
  file: string;
  line: number;
  anchored: boolean;
}

/**
 * The source is parsed rather than grepped. A regex cannot tell a real attribute from the
 * string "data-guide" appearing in the guide's own prose, and the guide explains itself.
 */
function scan(files: string[]): { anchors: Found[]; computed: Found[]; interactive: Interactive[] } {
  const anchors: Found[] = [];
  const computed: Found[] = [];
  const interactive: Interactive[] = [];

  for (const file of files) {
    const text = readFileSync(file, "utf8");
    const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const rel = relative(process.cwd(), file).split(sep).join("/");
    const lineOf = (node: ts.Node) => sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1;

    /**
     * String literals in VALUE position. A conditional contributes only its branches, never its
     * condition, so `cls === "execution_gap" ? "config.cost-cfn" : undefined` yields one anchor
     * rather than two.
     */
    const valueLiterals = (node: ts.Node): string[] => {
      if (ts.isStringLiteral(node)) return [node.text];
      if (ts.isParenthesizedExpression(node)) return valueLiterals(node.expression);
      if (ts.isConditionalExpression(node)) return [...valueLiterals(node.whenTrue), ...valueLiterals(node.whenFalse)];
      if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken) {
        return [...valueLiterals(node.left), ...valueLiterals(node.right)];
      }
      return [];
    };

    /** Only a built string breaks reconciliation. A bare identifier is a forwarding prop, and
     *  the literal it eventually receives is scanned at the call site. */
    const buildsAString = (node: ts.Node): boolean => {
      let built = false;
      const visit = (n: ts.Node) => {
        if (ts.isTemplateExpression(n) || ts.isNoSubstitutionTemplateLiteral(n)) built = true;
        if (ts.isBinaryExpression(n) && n.operatorToken.kind === ts.SyntaxKind.PlusToken) built = true;
        ts.forEachChild(n, visit);
      };
      visit(node);
      return built;
    };

    const ANCHOR_NAMES = new Set(["data-guide", "guide", "tableGuide", "firstRowGuide"]);

    /** One rule for JSX attributes, object properties and destructured parameter defaults. */
    const record = (name: string, value: ts.Node | undefined, at: ts.Node) => {
      if (!ANCHOR_NAMES.has(name) || !value) return;
      const expr = ts.isJsxExpression(value) ? value.expression : value;
      if (!expr) return;
      const values = valueLiterals(expr);
      for (const v of values) anchors.push({ anchor: v, file: rel, line: lineOf(at) });
      if (!values.length && buildsAString(expr)) computed.push({ anchor: at.getText(sf), file: rel, line: lineOf(at) });
    };

    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "guide") {
        const arg = node.arguments[0];
        if (arg && ts.isStringLiteral(arg)) anchors.push({ anchor: arg.text, file: rel, line: lineOf(node) });
        else if (arg && buildsAString(arg)) computed.push({ anchor: arg.getText(sf), file: rel, line: lineOf(node) });
      }
      if (ts.isPropertyAssignment(node)) record(node.name.getText(sf), node.initializer, node);
      if (ts.isBindingElement(node) && node.initializer) record(node.name.getText(sf), node.initializer, node);

      if (ts.isJsxOpeningLikeElement(node)) {
        const tag = node.tagName.getText(sf);
        let hasHandler = false;
        for (const attr of node.attributes.properties) {
          if (ts.isJsxSpreadAttribute(attr)) continue; // {...guide("…")} is the CallExpression above
          if (!ts.isJsxAttribute(attr)) continue;
          const name = attr.name.getText(sf);
          record(name, attr.initializer, attr);
          if (name === "onClick" || name === "onChange") hasHandler = true;
        }
        const isControlTag = ["Button", "Select", "button", "select", "input", "textarea"].includes(tag);
        // The guide's own chrome (spotlight panels, popover buttons, help panel) is not part of
        // the supervisory workflow and is not described by itself.
        const isGuideChrome = rel.startsWith("src/guide/components/");
        if ((isControlTag || hasHandler) && !isGuideChrome) {
          // Any mention of an anchor anywhere in the opening tag counts, which covers the Tabs
          // pattern where the anchors live inside an array prop.
          const anchored = /\bdata-guide\b|\bguide[:=(]|\btableGuide\b|\bfirstRowGuide\b/.test(node.getText(sf));
          interactive.push({ symbol: tag, file: rel, line: lineOf(node), anchored });
        }
      }

      ts.forEachChild(node, visit);
    };
    visit(sf);
  }
  return { anchors, computed, interactive };
}

const FILES = walk(SRC);
const { anchors, computed, interactive } = scan(FILES);

describe("guide model", () => {
  it("is internally consistent", () => {
    expect(() => assertModelIntegrity()).not.toThrow();
  });

  it("describes every anchor that appears in the source", () => {
    const orphans = anchors.filter((a) => !BY_ANCHOR.has(a.anchor));
    expect(
      orphans.map((a) => `${a.file}:${a.line} has data-guide="${a.anchor}", which src/guide/content.ts does not describe`),
    ).toEqual([]);
  });

  it("anchors every control it describes", () => {
    const placed = new Set(anchors.map((a) => a.anchor));
    const missing = ALL_ANCHORS.filter((a) => !placed.has(a) && !BY_ANCHOR.get(a)!.control.undocumentedInDom);
    expect(missing.map((a) => `content.ts describes "${a}" but no element in src/ carries it`)).toEqual([]);
  });

  it("uses only literal anchors", () => {
    expect(computed.map((c) => `${c.file}:${c.line} computes its guide anchor (${c.anchor}); use a string literal`)).toEqual([]);
  });

  it("points every screen at a real route", () => {
    const bad = ROUTE_SCREENS.filter((s) => !ROUTE_PATHS.includes(s.routePattern));
    expect(bad.map((s) => `screen "${s.id}" claims route ${s.routePattern}, which the router does not serve`)).toEqual([]);
  });

  /** Where each screen's code lives. Explicit rather than inferred, so a rename fails loudly. */
  const SCREEN_SOURCES: Record<string, readonly string[]> = {
    portfolio: ["src/features/portfolio/PortfolioPage.tsx", "src/components/charts/RiskHeatmap.tsx"],
    entity: ["src/features/entity/EntityPage.tsx"],
    findings: ["src/features/finding/FindingsListPage.tsx"],
    finding: ["src/features/finding/FindingPage.tsx"],
    queue: ["src/features/queue/QueuePage.tsx"],
    peer: ["src/features/peer/PeerPage.tsx"],
    coverage: ["src/features/coverage/CoveragePage.tsx"],
    trends: ["src/features/trends/TrendsPage.tsx"],
    ingestion: ["src/features/ingestion/IngestionPage.tsx"],
    config: ["src/features/config/ConfigPage.tsx"],
    audit: ["src/features/audit/AuditPage.tsx"],
    reports: ["src/features/reports/ReportsPage.tsx"],
    guide: ["src/guide/GuidePage.tsx"],
  };

  it("names URL parameters the screen actually uses", () => {
    const problems: string[] = [];
    for (const screen of ROUTE_SCREENS) {
      const paths = SCREEN_SOURCES[screen.id];
      if (!paths) {
        problems.push(`screen "${screen.id}" has no entry in SCREEN_SOURCES`);
        continue;
      }
      const text = paths
        .map((p) => {
          try {
            return readFileSync(join(process.cwd(), p), "utf8");
          } catch {
            problems.push(`SCREEN_SOURCES names ${p}, which does not exist`);
            return "";
          }
        })
        .join("\n");
      for (const control of screen.controls) {
        for (const p of control.writesParams ?? []) {
          const used =
            text.includes(`useSearchParamState("${p.param}"`) ||
            text.includes(`param="${p.param}"`) ||
            (p.param === "period" && text.includes("usePeriodParam")) ||
            new RegExp(`\\b${p.param}=\\$|[?&]${p.param}=`).test(text) ||
            // Some screens choose the key at run time, e.g. the heatmap writing either
            // ?dimension= or ?capability= depending on the lens. The name still has to appear.
            text.includes(`"${p.param}"`);
          if (!used) {
            problems.push(`${anchorOf(screen, control)} claims to write ?${p.param}, which does not appear in ${paths.join(" or ")}`);
          }
        }
      }
    }
    expect(problems).toEqual([]);
  });

  it("keeps tours and navigation in step with the model", () => {
    const problems: string[] = [];
    for (const tour of TOURS) {
      tour.steps.forEach((step, i) => {
        if (!BY_ANCHOR.has(step.anchor)) problems.push(`tour ${tour.id} step ${i} points at unknown anchor "${step.anchor}"`);
        if (!ROUTE_PATHS.includes(step.routePattern)) problems.push(`tour ${tour.id} step ${i} claims route ${step.routePattern}`);
        for (const action of step.before ?? []) {
          if (action.type === "click" && !BY_ANCHOR.has(action.anchor)) {
            problems.push(`tour ${tour.id} step ${i} clicks unknown anchor "${action.anchor}"`);
          }
        }
      });
    }
    for (const item of NAV_ITEMS) {
      if (!SCREENS.some((s) => s.navKey === item.key)) problems.push(`nav item "${item.key}" has no screen in content.ts`);
    }
    expect(problems).toEqual([]);
  });

  it("has a documented reason for every undescribed control", () => {
    const exempt = new Set(EXEMPT_CONTROLS.map((e) => `${e.file}::${e.symbol}`));
    const undocumented = interactive.filter((i) => !i.anchored && !exempt.has(`${i.file}::${i.symbol}`));
    expect(
      undocumented.map(
        (i) => `${i.file}:${i.line} <${i.symbol}> is interactive but neither anchored nor listed in src/guide/exempt.ts`,
      ),
    ).toEqual([]);
  });
});
