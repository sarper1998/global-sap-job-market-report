import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "dist");
const html = await readFile(path.join(root, "index.html"), "utf8");
const hosting = await readFile(path.join(root, ".openai", "hosting.json"), "utf8");
const sapJobsCsv = await readFile(path.join(root, "data", "processed", "sap_jobs.csv"), "utf8");
const sapJobsJson = await readFile(path.join(root, "data", "processed", "sap_jobs.json"), "utf8");
const summaryJson = await readFile(path.join(root, "data", "processed", "summary.json"), "utf8");
const linkedInSignalJson = await readFile(path.join(root, "data", "processed", "linkedin_signal.json"), "utf8");
const linkedInJobsCsv = await readFile(path.join(root, "data", "processed", "linkedin_jobs.csv"), "utf8");
const linkedInJobsJson = await readFile(path.join(root, "data", "processed", "linkedin_jobs.json"), "utf8");
const linkedInJobsSummaryJson = await readFile(path.join(root, "data", "processed", "linkedin_jobs_summary.json"), "utf8");
const snapshotIndexJson = await readFile(path.join(root, "data", "snapshots", "index.json"), "utf8");

await rm(dist, { recursive: true, force: true });
await mkdir(path.join(dist, "server"), { recursive: true });
await mkdir(path.join(dist, ".openai"), { recursive: true });
await writeFile(path.join(dist, ".openai", "hosting.json"), hosting);

const server = `const html = ${JSON.stringify(html)};
const files = new Map([
  ["/data/sap_jobs.csv", { body: ${JSON.stringify(sapJobsCsv)}, type: "text/csv; charset=utf-8" }],
  ["/data/sap_jobs.json", { body: ${JSON.stringify(sapJobsJson)}, type: "application/json; charset=utf-8" }],
  ["/data/summary.json", { body: ${JSON.stringify(summaryJson)}, type: "application/json; charset=utf-8" }],
  ["/data/linkedin_signal.json", { body: ${JSON.stringify(linkedInSignalJson)}, type: "application/json; charset=utf-8" }],
  ["/data/linkedin_jobs.csv", { body: ${JSON.stringify(linkedInJobsCsv)}, type: "text/csv; charset=utf-8" }],
  ["/data/linkedin_jobs.json", { body: ${JSON.stringify(linkedInJobsJson)}, type: "application/json; charset=utf-8" }],
  ["/data/linkedin_jobs_summary.json", { body: ${JSON.stringify(linkedInJobsSummaryJson)}, type: "application/json; charset=utf-8" }],
  ["/data/snapshots/index.json", { body: ${JSON.stringify(snapshotIndexJson)}, type: "application/json; charset=utf-8" }]
]);

function response(body, contentType) {
  return new Response(body, {
    headers: {
      "content-type": contentType,
      "cache-control": "public, max-age=300"
    }
  });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const file = files.get(url.pathname);
    if (file) {
      return response(file.body, file.type);
    }
    if (url.pathname === "/" || url.pathname === "/index.html") {
      return response(html, "text/html; charset=utf-8");
    }
    return response(html, "text/html; charset=utf-8");
  }
};
`;

await writeFile(path.join(dist, "server", "index.js"), server);
console.log("Built dist/server/index.js");
