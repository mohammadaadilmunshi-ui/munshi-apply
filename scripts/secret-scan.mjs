import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const tracked = execFileSync(
  "git",
  ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
  {
    encoding: "utf8",
  },
)
  .split("\0")
  .filter(Boolean);

const binaryExtensions = new Set([
  ".gif",
  ".ico",
  ".jpeg",
  ".jpg",
  ".pdf",
  ".png",
  ".webp",
  ".zip",
]);
const allowedPlaceholders = new Set(["apps/native-host/.env.example"]);
const patterns = [
  ["private key", /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/],
  ["GitHub token", /\bgh[opsu]_[A-Za-z0-9]{30,}\b/],
  ["AWS access key", /\bAKIA[0-9A-Z]{16}\b/],
  ["OpenAI API key", /\bsk-[A-Za-z0-9_-]{20,}\b/],
  [
    "generic secret assignment",
    /\b(?:api[_-]?key|password|secret|token)\s*[:=]\s*["'][^"'\s]{12,}["']/i,
  ],
];

const findings = [];
for (const file of tracked) {
  const extension = file.slice(file.lastIndexOf(".")).toLowerCase();
  if (binaryExtensions.has(extension) || allowedPlaceholders.has(file))
    continue;
  let content;
  try {
    content = readFileSync(file, "utf8");
  } catch {
    continue;
  }
  for (const [label, pattern] of patterns) {
    if (pattern.test(content)) findings.push(`${file}: ${label}`);
  }
}

if (findings.length > 0) {
  throw new Error(`Potential secrets detected:\n${findings.join("\n")}`);
}

console.log(`Secret scan passed for ${tracked.length} tracked files.`);
