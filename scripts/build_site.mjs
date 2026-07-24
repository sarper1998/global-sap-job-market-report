import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(root, "dist");
const html = await readFile(path.join(root, "index.html"), "utf8");
const distHtml = html.replaceAll('href="data/processed/', 'href="data/');
const hosting = await readFile(path.join(root, ".openai", "hosting.json"), "utf8");

await rm(dist, { recursive: true, force: true });
await mkdir(path.join(dist, "server"), { recursive: true });
await mkdir(path.join(dist, ".openai"), { recursive: true });
await writeFile(path.join(dist, ".openai", "hosting.json"), hosting);
await writeFile(path.join(dist, "index.html"), distHtml);

const server = `const html = ${JSON.stringify(distHtml)};
function htmlResponse(body) {
  return new Response(body, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "public, max-age=300"
    }
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/index.html") {
      return htmlResponse(html);
    }
    if (env && env.ASSETS && typeof env.ASSETS.fetch === "function") {
      const assetResponse = await env.ASSETS.fetch(request);
      if (assetResponse.status !== 404) {
        return assetResponse;
      }
    }
    return htmlResponse(html);
  }
};
`;

await writeFile(path.join(dist, "server", "index.js"), server);
console.log("Built dist/index.html and dist/server/index.js");
