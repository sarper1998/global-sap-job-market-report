import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "dist");
const html = await readFile(path.join(root, "index.html"), "utf8");
const hosting = await readFile(path.join(root, ".openai", "hosting.json"), "utf8");

const dataFiles = [
  ["data/processed/sap_jobs.csv", "data/sap_jobs.csv"],
  ["data/processed/sap_jobs.json", "data/sap_jobs.json"],
  ["data/processed/summary.json", "data/summary.json"],
  ["data/processed/linkedin_signal.json", "data/linkedin_signal.json"],
  ["data/processed/linkedin_jobs.csv", "data/linkedin_jobs.csv"],
  ["data/processed/linkedin_jobs.csv.gz", "data/linkedin_jobs.csv.gz"],
  ["data/processed/linkedin_jobs.json.gz", "data/linkedin_jobs.json.gz"],
  ["data/processed/linkedin_jobs_summary.json", "data/linkedin_jobs_summary.json"],
  ["data/processed/company_career_jobs.csv", "data/company_career_jobs.csv"],
  ["data/processed/company_career_jobs.json", "data/company_career_jobs.json"],
  ["data/processed/company_career_jobs_summary.json", "data/company_career_jobs_summary.json"],
  ["data/processed/daily_delta_summary.json", "data/daily_delta_summary.json"],
  ["data/snapshots/index.json", "data/snapshots/index.json"]
];

await rm(dist, { recursive: true, force: true });
await mkdir(path.join(dist, "server"), { recursive: true });
await mkdir(path.join(dist, ".openai"), { recursive: true });
await mkdir(path.join(dist, "data", "snapshots"), { recursive: true });
await writeFile(path.join(dist, ".openai", "hosting.json"), hosting);
await writeFile(path.join(dist, "index.html"), html);

for (const [source, target] of dataFiles) {
  const sourcePath = path.join(root, source);
  const targetPath = path.join(dist, target);
  await mkdir(path.dirname(targetPath), { recursive: true });
  await copyFile(sourcePath, targetPath).catch(() => {});
}

const server = `const html = ${JSON.stringify(html)};
function htmlResponse(body) {
  return new Response(body, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "public, max-age=300"
    }
  });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/index.html") {
      return htmlResponse(html);
    }
    return htmlResponse(html);
  }
};
`;

await writeFile(path.join(dist, "server", "index.js"), server);
console.log("Built dist/index.html, dist/data, and dist/server/index.js");
