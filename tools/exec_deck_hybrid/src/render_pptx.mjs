import fs from "node:fs";
import path from "node:path";

import pptxgen from "pptxgenjs";

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

function hexColor(value, fallback) {
  if (typeof value !== "string" || value.trim() === "") {
    return fallback;
  }
  return value.replace("#", "").toUpperCase();
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

function formatCurrency(value) {
  return `JPY ${Number(value).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function formatPct(value) {
  return `${(Number(value) * 100).toFixed(2)}%`;
}

const args = parseArgs(process.argv);
const specPath = requireArg(args, "spec");
const outPath = requireArg(args, "out");
const metricsOutPath = requireArg(args, "metrics-out");

const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const style = spec.style ?? {};
const colors = style.colors ?? {};
const fonts = style.fonts ?? {};
const typography = style.typography ?? {};
const layout = style.layout ?? {};
const slideSize = layout.slide_size_in ?? { width: 13.333, height: 7.5 };
const margins = layout.margins_in ?? { left: 0.6, right: 0.6, top: 0.35, bottom: 0.3 };

const colorPrimary = hexColor(colors.primary, "0B5FA5");
const colorSecondary = hexColor(colors.secondary, "5B6B7A");
const colorAccent = hexColor(colors.accent, "F59E0B");
const colorPositive = hexColor(colors.positive, "2A9D8F");
const colorNegative = hexColor(colors.negative, "D1495B");
const colorBackground = hexColor(colors.background, "F8FAFC");
const colorText = hexColor(colors.text, "111827");
const colorGrid = hexColor(colors.grid, "D1D5DB");

const fontJa = fonts.ja_primary ?? "Meiryo UI";
const fontEn = fonts.en_primary ?? "Calibri";
const titlePt = Number(typography.title_pt ?? 34);
const subtitlePt = Number(typography.subtitle_pt ?? 18);
const bodyPt = Number(typography.body_pt ?? 16);
const notePt = Number(typography.note_pt ?? 11);
const kpiPt = Number(typography.kpi_pt ?? 44);

const left = Number(margins.left ?? 0.6);
const top = Number(margins.top ?? 0.35);
const width = Number(slideSize.width ?? 13.333) - left - Number(margins.right ?? 0.6);

const counts = {
  total_shape_count: 0,
  editable_shape_count: 0,
};
function trackEditableShape() {
  counts.total_shape_count += 1;
  counts.editable_shape_count += 1;
}

const slides = Array.isArray(spec.slides) ? spec.slides : [];

const pptx = new pptxgen();
pptx.defineLayout({
  name: "CUSTOM",
  width: Number(slideSize.width ?? 13.333),
  height: Number(slideSize.height ?? 7.5),
});
pptx.layout = "CUSTOM";
pptx.author = "pricing-automation";
pptx.company = "pricing-automation";
pptx.subject = "Executive pricing deck";
pptx.title = "Executive pricing deck";

function addSlideHeader(slide, index) {
  const specSlide = slides[index] ?? { title: `Slide ${index + 1}`, message: "" };
  slide.background = { color: colorBackground };
  slide.addShape(pptx.ShapeType.roundRect, {
    x: left,
    y: top,
    w: width,
    h: 0.85,
    fill: { color: colorPrimary },
    line: { color: colorPrimary },
    radius: 0.04,
  });
  trackEditableShape();
  slide.addText(specSlide.title, {
    x: left + 0.18,
    y: top + 0.12,
    w: width - 0.35,
    h: 0.32,
    fontFace: fontEn,
    fontSize: titlePt * 0.45,
    bold: true,
    color: "FFFFFF",
  });
  trackEditableShape();
  slide.addText(specSlide.message, {
    x: left + 0.18,
    y: top + 0.45,
    w: width - 0.35,
    h: 0.22,
    fontFace: fontJa,
    fontSize: subtitlePt * 0.62,
    color: "FFFFFF",
  });
  trackEditableShape();
}

function addFooter(slide) {
  slide.addText("Source: out/run_summary_executive.json", {
    x: left,
    y: 7.16,
    w: width,
    h: 0.2,
    align: "right",
    fontFace: fontEn,
    fontSize: notePt,
    color: colorSecondary,
  });
  trackEditableShape();
}

function addExecutiveSummary() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 0);

  slide.addText(spec.headline ?? "", {
    x: left,
    y: 1.35,
    w: width,
    h: 0.65,
    fontFace: fontJa,
    fontSize: subtitlePt,
    color: colorText,
    bold: true,
  });
  trackEditableShape();

  const claims = Array.isArray(spec.summary_claims) ? spec.summary_claims : [];
  const cardGap = 0.14;
  const cardCount = claims.length > 0 ? claims.length : 1;
  const cardWidth = (width - cardGap * (cardCount - 1)) / cardCount;
  for (let i = 0; i < claims.length; i += 1) {
    const cardX = left + i * (cardWidth + cardGap);
    const claim = claims[i];
    slide.addShape(pptx.ShapeType.roundRect, {
      x: cardX,
      y: 2.25,
      w: cardWidth,
      h: 2.1,
      fill: { color: "FFFFFF" },
      line: { color: colorGrid },
      radius: 0.03,
    });
    trackEditableShape();
    slide.addText(claim.label ?? "", {
      x: cardX + 0.15,
      y: 2.45,
      w: cardWidth - 0.3,
      h: 0.45,
      fontFace: fontJa,
      fontSize: bodyPt * 0.9,
      color: colorSecondary,
    });
    trackEditableShape();
    slide.addText(formatClaimValue(claim), {
      x: cardX + 0.15,
      y: 2.95,
      w: cardWidth - 0.3,
      h: 0.95,
      fontFace: fontEn,
      fontSize: kpiPt * 0.45,
      bold: true,
      color: colorPrimary,
    });
    trackEditableShape();
  }
  addFooter(slide);
}

function addDecisionStatement() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 1);

  const asks = Array.isArray(spec.decision_asks) ? spec.decision_asks : [];
  const bulletLines = asks.map((item) => `• ${item}`).join("\n");
  slide.addText(bulletLines, {
    x: left + 0.1,
    y: 1.5,
    w: width - 0.2,
    h: 3.6,
    fontFace: fontJa,
    fontSize: bodyPt,
    color: colorText,
    valign: "top",
    breakLine: true,
  });
  trackEditableShape();
  slide.addShape(pptx.ShapeType.line, {
    x: left,
    y: 5.35,
    w: width,
    h: 0,
    line: { color: colorGrid, pt: 1 },
  });
  trackEditableShape();
  slide.addText(`Config: ${spec.meta?.config_path ?? "-"}`, {
    x: left,
    y: 5.45,
    w: width,
    h: 0.8,
    fontFace: fontEn,
    fontSize: notePt * 1.1,
    color: colorSecondary,
  });
  trackEditableShape();
  addFooter(slide);
}

function addPricingRecommendation() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 2);
  const rows = [["model_point", "annual_P", "monthly_P", "IRR", "NBV", "PTM"]];
  for (const row of spec.pricing_table ?? []) {
    rows.push([
      String(row.model_point),
      Number(row.gross_annual_premium).toLocaleString("en-US"),
      Number(row.monthly_premium).toLocaleString("en-US", { maximumFractionDigits: 1 }),
      formatPct(row.irr),
      Number(row.nbv).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      Number(row.premium_to_maturity).toFixed(4),
    ]);
  }
  slide.addTable(rows, {
    x: left,
    y: 1.45,
    w: width,
    h: 4.85,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: colorBackground,
    color: colorText,
    fontFace: fontEn,
    fontSize: bodyPt * 0.65,
    autoFit: true,
    valign: "middle",
  });
  trackEditableShape();
  addFooter(slide);
}

function addConstraintStatus() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 3);
  const rows = [["constraint", "threshold", "min_gap", "worst_mp", "status"]];
  for (const row of spec.constraint_status ?? []) {
    rows.push([
      String(row.label ?? row.constraint),
      Number(row.threshold).toLocaleString("en-US", { maximumFractionDigits: 6 }),
      Number(row.min_gap).toLocaleString("en-US", { maximumFractionDigits: 6 }),
      String(row.worst_model_point),
      row.all_ok ? "OK" : "NG",
    ]);
  }
  slide.addTable(rows, {
    x: left,
    y: 1.45,
    w: width,
    h: 4.85,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: "FFFFFF",
    color: colorText,
    fontFace: fontJa,
    fontSize: bodyPt * 0.64,
  });
  trackEditableShape();
  addFooter(slide);
}

function addCashflowBridge() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 4);
  const rows = Array.isArray(spec.cashflow_by_source) ? spec.cashflow_by_source : [];
  const labels = rows.map((row) => `Y${row.year}`);
  const premium = rows.map((row) => Number(row.premium_income));
  const investment = rows.map((row) => Number(row.investment_income));
  const benefit = rows.map((row) => Number(row.benefit_outgo));
  const expense = rows.map((row) => Number(row.expense_outgo));
  const reserve = rows.map((row) => Number(row.reserve_change_outgo));
  const net = rows.map((row) => Number(row.net_cf));

  slide.addChart(
    pptx.ChartType.bar,
    [
      { name: "Premium", labels, values: premium },
      { name: "Investment", labels, values: investment },
      { name: "Benefit", labels, values: benefit },
      { name: "Expense", labels, values: expense },
      { name: "Reserve", labels, values: reserve },
    ],
    {
      x: left,
      y: 1.45,
      w: width,
      h: 3.9,
      barGrouping: "stacked",
      fontFace: fontEn,
      fontSize: bodyPt * 0.6,
      catAxisLabelRotate: 0,
      showLegend: true,
      legendPos: "t",
      chartColors: [colorPrimary, colorPositive, colorNegative, colorAccent, colorSecondary],
    }
  );
  trackEditableShape();

  slide.addChart(
    pptx.ChartType.line,
    [{ name: "Net CF", labels, values: net }],
    {
      x: left,
      y: 5.45,
      w: width,
      h: 1.35,
      fontFace: fontEn,
      fontSize: bodyPt * 0.55,
      showLegend: false,
      lineSize: 2,
      chartColors: [hexColor("#111111", "111111")],
    }
  );
  trackEditableShape();
  addFooter(slide);
}

function pickKeyCashflowRows(rows) {
  if (rows.length <= 5) {
    return rows;
  }
  const indexes = [0, Math.floor(rows.length * 0.25), Math.floor(rows.length * 0.5), Math.floor(rows.length * 0.75), rows.length - 1];
  const deduped = [...new Set(indexes)];
  return deduped.map((index) => rows[index]);
}

function addProfitSourceDecomposition() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 5);
  const rows = pickKeyCashflowRows(Array.isArray(spec.cashflow_by_source) ? spec.cashflow_by_source : []);
  const tableRows = [["year", "premium", "investment", "benefit", "expense", "reserve", "net_cf"]];
  for (const row of rows) {
    tableRows.push([
      `Y${row.year}`,
      formatCurrency(row.premium_income),
      formatCurrency(row.investment_income),
      formatCurrency(row.benefit_outgo),
      formatCurrency(row.expense_outgo),
      formatCurrency(row.reserve_change_outgo),
      formatCurrency(row.net_cf),
    ]);
  }
  slide.addTable(tableRows, {
    x: left,
    y: 1.45,
    w: width,
    h: 4.25,
    border: { type: "solid", pt: 1, color: colorGrid },
    fontFace: fontEn,
    fontSize: bodyPt * 0.58,
    color: colorText,
    fill: "FFFFFF",
  });
  trackEditableShape();
  slide.addText("Key years only. Full yearly detail is available in Markdown appendix.", {
    x: left,
    y: 5.95,
    w: width,
    h: 0.45,
    fontFace: fontEn,
    fontSize: notePt * 1.05,
    color: colorSecondary,
  });
  trackEditableShape();
  addFooter(slide);
}

function addSensitivity() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 6);
  const rows = [["scenario", "min_irr", "min_nbv", "max_ptm", "violations"]];
  for (const row of spec.sensitivity ?? []) {
    rows.push([
      String(row.scenario),
      formatPct(row.min_irr),
      formatCurrency(row.min_nbv),
      Number(row.max_premium_to_maturity).toFixed(4),
      `${Math.round(Number(row.violation_count))}`,
    ]);
  }
  slide.addTable(rows, {
    x: left,
    y: 1.45,
    w: width,
    h: 4.4,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: "FFFFFF",
    color: colorText,
    fontFace: fontEn,
    fontSize: bodyPt * 0.62,
  });
  trackEditableShape();
  addFooter(slide);
}

function addGovernance() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 7);
  const traceRows = Array.isArray(spec.trace_map) ? spec.trace_map : [];
  const previewTrace = traceRows.slice(0, 6);
  const lines = previewTrace.map(
    (row) => `• ${row.claim_id}: ${row.source_file} ${row.source_path}`
  );
  if (traceRows.length > previewTrace.length) {
    lines.push(`• ... and ${traceRows.length - previewTrace.length} more traced claims`);
  }
  slide.addText(lines.join("\n"), {
    x: left,
    y: 1.55,
    w: width,
    h: 4.8,
    fontFace: fontEn,
    fontSize: bodyPt * 0.74,
    color: colorText,
    breakLine: true,
    valign: "top",
  });
  trackEditableShape();
  addFooter(slide);
}

function addDecisionAsk() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 8);
  const asks = Array.isArray(spec.decision_asks) ? spec.decision_asks : [];
  const lines = asks.map((row) => `• ${row}`);
  lines.push("• Monitoring trigger: min_irr < 2.0% OR max PTM > 1.056");
  slide.addText(lines.join("\n"), {
    x: left,
    y: 1.5,
    w: width,
    h: 4.8,
    fontFace: fontJa,
    fontSize: bodyPt * 0.95,
    color: colorText,
    breakLine: true,
    valign: "top",
  });
  trackEditableShape();
  slide.addShape(pptx.ShapeType.roundRect, {
    x: left,
    y: 6.35,
    w: width,
    h: 0.62,
    fill: { color: colorAccent, transparency: 88 },
    line: { color: colorAccent, pt: 1 },
    radius: 0.03,
  });
  trackEditableShape();
  slide.addText("All quantitative claims are traceable via out/executive_deck_spec.json trace_map.", {
    x: left + 0.15,
    y: 6.5,
    w: width - 0.3,
    h: 0.3,
    fontFace: fontEn,
    fontSize: notePt,
    color: colorSecondary,
  });
  trackEditableShape();
  addFooter(slide);
}

addExecutiveSummary();
addDecisionStatement();
addPricingRecommendation();
addConstraintStatus();
addCashflowBridge();
addProfitSourceDecomposition();
addSensitivity();
addGovernance();
addDecisionAsk();

fs.mkdirSync(path.dirname(outPath), { recursive: true });
await pptx.writeFile({ fileName: outPath });

counts.slide_count = 9;
fs.mkdirSync(path.dirname(metricsOutPath), { recursive: true });
fs.writeFileSync(metricsOutPath, JSON.stringify(counts, null, 2), "utf8");
