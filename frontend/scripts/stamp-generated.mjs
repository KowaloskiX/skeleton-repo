/**
 * Stamps the generated client with an `@ts-nocheck` header.
 *
 * Why: code from @hey-api/openapi-ts does not pass `exactOptionalPropertyTypes: true`
 * (it passes `T | undefined` into optional fields). The choice is between weakening the
 * tsconfig for the WHOLE frontend and disabling checks in files we do not write — we take the
 * latter. The types these files export still work, so every use of the API on our side is
 * fully typed.
 *
 * The script is idempotent: running it twice does not duplicate the header.
 */
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const GENERATED_DIR = new URL("../src/lib/api/generated", import.meta.url).pathname;
const HEADER = [
  "// GENERATED FILE — do not edit by hand.",
  "// Regenerate: uv run dump-openapi (backend) + pnpm --filter web generate:api",
  "// @ts-nocheck",
  "",
].join("\n");

async function* walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) yield* walk(path);
    else if (entry.name.endsWith(".ts")) yield path;
  }
}

let stamped = 0;
for await (const path of walk(GENERATED_DIR)) {
  const source = await readFile(path, "utf8");
  if (source.startsWith("// GENERATED FILE")) continue;
  await writeFile(path, HEADER + source, "utf8");
  stamped += 1;
}

console.log(`Stamped ${stamped} generated files.`);
