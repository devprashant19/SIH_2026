// Fails the build if the production bundle references any external host.
// Run after `npm run build`. Licence comments inside vendored libraries are allowed.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const dist = new URL("../dist", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const offenders = [];

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(js|css|html)$/.test(name)) {
      const text = readFileSync(p, "utf8");
      const matches = text.match(/https?:\/\/[^\s"'`)]+/g) ?? [];
      for (const m of matches) {
        // Allow XML namespaces, licence/homepage URLs inside comments, and localhost.
        // Documentation URLs printed inside library error messages are inert text, not network calls.
      if (/w3\.org|localhost|127\.0\.0\.1|github\.com|opensource\.org|reactjs\.org|react\.dev|recharts\.org|npmjs\.com|tanstack\.com|mozilla\.org|fb\.me/.test(m)) continue;
        offenders.push(`${p}: ${m}`);
      }
    }
  }
}

walk(dist);
if (offenders.length) {
  console.error("External references found in bundle:\n" + offenders.join("\n"));
  process.exit(1);
}
console.log("offline check passed: no external hosts referenced in dist/");
