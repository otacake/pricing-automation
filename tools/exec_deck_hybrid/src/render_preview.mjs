import fs from "node:fs";
import path from "node:path";

function parseArgs(argv) {
  const parsed = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
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
  if (!value) throw new Error(`Missing required argument: --${key}`);
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

function asStringArray(value) {
  return (Array.isArray(value) ? value : [])
    .map((item) => String(item).trim())
    .filter((item) => item.length > 0);
}

function formatClaimValue(item) {
  const value = Number(item.value ?? 0);
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
      return `${item.value ?? "-"}`;
  }
}

function replaceAllTokens(template, replacements) {
  let output = template;
  for (const [token, value] of Object.entries(replacements)) {
    output = output.split(`{{${token}}}`).join(value);
  }
  return output;
}

function narrativeToListItems(block, isJa) {
  if (!block || typeof block !== "object") return "<li>-</li>";
  const rows = [];
  const conclusion = String(block.conclusion ?? "").trim();
  if (conclusion) rows.push(`${isJa ? "結論" : "Conclusion"}: ${conclusion}`);
  asStringArray(block.rationale).forEach((item, index) => rows.push(`${isJa ? `根拠${index + 1}` : `Rationale ${index + 1}`}: ${item}`));
  asStringArray(block.risk).forEach((item) => rows.push(`${isJa ? "リスク" : "Risk"}: ${item}`));
  asStringArray(block.decision_ask).forEach((item) => rows.push(`${isJa ? "意思決定要請" : "Decision Ask"}: ${item}`));
  if (rows.length === 0) return "<li>-</li>";
  return rows.map((row) => `<li>${escapeHtml(row)}</li>`).join("\n");
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
const isJa = (spec.meta?.language ?? "ja") === "ja";

css = replaceAllTokens(css, {
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
});

const summaryCards = (spec.summary_claims ?? [])
  .map((item) => `<article class="card"><span class="label">${escapeHtml(item.label)}</span><span class="value">${escapeHtml(formatClaimValue(item))}</span></article>`)
  .join("\n");

const pricingRows = (spec.pricing_table ?? [])
  .map((row) => `<tr><td>${escapeHtml(row.model_point)}</td><td>${Number(row.gross_annual_premium).toLocaleString("en-US")}</td><td>${Number(row.monthly_premium).toLocaleString("en-US", { maximumFractionDigits: 1 })}</td><td>${(Number(row.irr) * 100).toFixed(2)}%</td><td>${Number(row.nbv).toLocaleString("en-US", { maximumFractionDigits: 0 })}</td><td>${Number(row.premium_to_maturity).toFixed(4)}</td></tr>`)
  .join("\n");

const constraintRows = (spec.constraint_status ?? [])
  .map((row) => `<tr><td>${escapeHtml(row.label ?? row.constraint)}</td><td>${Number(row.threshold).toLocaleString("en-US", { maximumFractionDigits: 6 })}</td><td>${Number(row.min_gap).toLocaleString("en-US", { maximumFractionDigits: 6 })}</td><td>${escapeHtml(row.worst_model_point)}</td><td>${row.all_ok ? "OK" : "NG"}</td></tr>`)
  .join("\n");

const sensitivityRows = (spec.sensitivity ?? [])
  .map((row) => `<tr><td>${escapeHtml(row.scenario)}</td><td>${(Number(row.min_irr) * 100).toFixed(2)}%</td><td>${Number(row.min_nbv).toLocaleString("en-US", { maximumFractionDigits: 0 })}</td><td>${Number(row.max_premium_to_maturity).toFixed(4)}</td><td>${Math.round(Number(row.violation_count))}</td></tr>`)
  .join("\n");

const compare = spec.decision_compare ?? {};
const compareSummary = asStringArray(compare.adoption_reason)
  .slice(0, 3)
  .map((line) => `<li>${escapeHtml(line)}</li>`)
  .join("\n");
const objectives = compare.objectives ?? {};
const compareObjectives = `recommended objective: ${String(objectives.recommended ?? "-")} / counter objective: ${String(objectives.counter ?? "-")}`;

const causalRows = ((spec.causal_bridge ?? {}).components ?? [])
  .map((row) => `<tr><td>${escapeHtml(row.label ?? row.component ?? "")}</td><td>${Number(row.recommended_total ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}</td><td>${Number(row.counter_total ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}</td><td>${Number(row.delta_recommended_minus_counter ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}</td></tr>`)
  .join("\n");

const mainSlideChecks = spec.main_slide_checks ?? {};
const mainSlideCheckRows = (Array.isArray(mainSlideChecks.per_slide) ? mainSlideChecks.per_slide : [])
  .map((row) => `<tr><td>${escapeHtml(row.slide_id ?? "")}</td><td>${Number(row.line_count ?? 0)}</td><td>${Boolean(row.required_sections_present ?? false)}</td><td>${Boolean(row.density_ok ?? false)}</td><td>${Boolean(row.section_order_ok ?? false)}</td></tr>`)
  .join("\n");
const mainSlideCheckSummary = `coverage=${Number(mainSlideChecks.coverage ?? 0).toFixed(3)}, density_ok=${String(Boolean(mainSlideChecks.density_ok))}, main_compare_present=${String(Boolean(mainSlideChecks.main_compare_present))}, decision_style_ok=${String(Boolean(mainSlideChecks.decision_style_ok))}`;

const narrativeMap = spec.management_narrative ?? {};

const html = replaceAllTokens(template, {
  THEME_CSS: css,
  HEADLINE: escapeHtml(spec.headline ?? ""),
  SUMMARY_CARDS: summaryCards,
  PRICING_ROWS: pricingRows,
  CONSTRAINT_ROWS: constraintRows,
  SENSITIVITY_ROWS: sensitivityRows,
  COMPARE_OBJECTIVES: escapeHtml(compareObjectives),
  COMPARE_SUMMARY: compareSummary || "<li>-</li>",
  CAUSAL_ROWS: causalRows,
  MAIN_SLIDE_CHECK_ROWS: mainSlideCheckRows || '<tr><td colspan="5">-</td></tr>',
  MAIN_SLIDE_CHECK_SUMMARY: escapeHtml(mainSlideCheckSummary),
  NARRATIVE_EXEC_SUMMARY: narrativeToListItems(narrativeMap.executive_summary, isJa),
  NARRATIVE_DECISION_STATEMENT: narrativeToListItems(narrativeMap.decision_statement, isJa),
  NARRATIVE_PRICING_RECOMMENDATION: narrativeToListItems(narrativeMap.pricing_recommendation, isJa),
  NARRATIVE_CONSTRAINT_STATUS: narrativeToListItems(narrativeMap.constraint_status, isJa),
  NARRATIVE_SENSITIVITY: narrativeToListItems(narrativeMap.sensitivity, isJa),
});

fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, html, "utf8");
