import fs from "node:fs";
import path from "node:path";

function parseArgs(argv) {
  const parsed = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) {
      continue;
    }
    const key = token.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      parsed[key] = "true";
      continue;
    }
    parsed[key] = next;
    i += 1;
  }
  return parsed;
}

function requireArg(args, key) {
  const value = args[key];
  if (!value) {
    throw new Error(`Missing required argument: --${key}`);
  }
  return value;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatClaimValue(item) {
  const value = Number(item.value);
  switch (item.format) {
    case "pct":
      return `${(value * 100).toFixed(2)}%`;
    case "currency_jpy":
      return `JPY ${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
    case "ratio":
      return value.toFixed(4);
    case "integer":
      return `${Math.round(value)}`;
    default:
      return `${item.value}`;
  }
}

function replaceAllTokens(template, replacements) {
  let output = template;
  for (const [token, value] of Object.entries(replacements)) {
    output = output.split(`{{${token}}}`).join(value);
  }
  return output;
}

const args = parseArgs(process.argv);
const specPath = requireArg(args, "spec");
const templatePath = requireArg(args, "template");
const cssPath = requireArg(args, "css");
const outPath = requireArg(args, "out");

const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const template = fs.readFileSync(templatePath, "utf8");
let css = fs.readFileSync(cssPath, "utf8");

const colors = spec?.style?.colors ?? {};
const fonts = spec?.style?.fonts ?? {};
const cssReplacements = {
  COLOR_PRIMARY: colors.primary ?? "#0B5FA5",
  COLOR_SECONDARY: colors.secondary ?? "#5B6B7A",
  COLOR_ACCENT: colors.accent ?? "#F59E0B",
  COLOR_POSITIVE: colors.positive ?? "#2A9D8F",
  COLOR_NEGATIVE: colors.negative ?? "#D1495B",
  COLOR_BACKGROUND: colors.background ?? "#F8FAFC",
  COLOR_TEXT: colors.text ?? "#111827",
  COLOR_GRID: colors.grid ?? "#D1D5DB",
  FONT_JA: fonts.ja_primary ?? "Meiryo UI",
  FONT_JA_FALLBACK: fonts.ja_fallback ?? "Meiryo",
  FONT_EN: fonts.en_primary ?? "Calibri",
  FONT_EN_FALLBACK: fonts.en_fallback ?? "Arial",
};
css = replaceAllTokens(css, cssReplacements);

const summaryCards = (spec.summary_claims ?? [])
  .map((item) => {
    return [
      '<article class="card">',
      `<span class="label">${escapeHtml(item.label)}</span>`,
      `<span class="value">${escapeHtml(formatClaimValue(item))}</span>`,
      "</article>",
    ].join("");
  })
  .join("\n");

const pricingRows = (spec.pricing_table ?? [])
  .map((row) => {
    return [
      "<tr>",
      `<td>${escapeHtml(row.model_point)}</td>`,
      `<td>${Number(row.gross_annual_premium).toLocaleString("en-US")}</td>`,
      `<td>${Number(row.monthly_premium).toLocaleString("en-US", { maximumFractionDigits: 1 })}</td>`,
      `<td>${(Number(row.irr) * 100).toFixed(2)}%</td>`,
      `<td>${Number(row.nbv).toLocaleString("en-US", { maximumFractionDigits: 0 })}</td>`,
      `<td>${Number(row.premium_to_maturity).toFixed(4)}</td>`,
      "</tr>",
    ].join("");
  })
  .join("\n");

const constraintRows = (spec.constraint_status ?? [])
  .map((row) => {
    return [
      "<tr>",
      `<td>${escapeHtml(row.label ?? row.constraint)}</td>`,
      `<td>${Number(row.threshold).toLocaleString("en-US", { maximumFractionDigits: 6 })}</td>`,
      `<td>${Number(row.min_gap).toLocaleString("en-US", { maximumFractionDigits: 6 })}</td>`,
      `<td>${escapeHtml(row.worst_model_point)}</td>`,
      `<td>${row.all_ok ? "OK" : "NG"}</td>`,
      "</tr>",
    ].join("");
  })
  .join("\n");

const sensitivityRows = (spec.sensitivity ?? [])
  .map((row) => {
    return [
      "<tr>",
      `<td>${escapeHtml(row.scenario)}</td>`,
      `<td>${(Number(row.min_irr) * 100).toFixed(2)}%</td>`,
      `<td>${Number(row.min_nbv).toLocaleString("en-US", { maximumFractionDigits: 0 })}</td>`,
      `<td>${Number(row.max_premium_to_maturity).toFixed(4)}</td>`,
      `<td>${Math.round(Number(row.violation_count))}</td>`,
      "</tr>",
    ].join("");
  })
  .join("\n");

const html = replaceAllTokens(template, {
  THEME_CSS: css,
  HEADLINE: escapeHtml(spec.headline ?? ""),
  SUMMARY_CARDS: summaryCards,
  PRICING_ROWS: pricingRows,
  CONSTRAINT_ROWS: constraintRows,
  SENSITIVITY_ROWS: sensitivityRows,
});

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, html, "utf8");
