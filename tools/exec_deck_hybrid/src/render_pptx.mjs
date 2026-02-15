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

function asStringArray(value) {
  return (Array.isArray(value) ? value : [])
    .map((item) => String(item).trim())
    .filter((item) => item.length > 0);
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

function bullets(lines) {
  return asStringArray(lines).map((line) => `- ${line}`).join("\n");
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
const isJa = (spec.meta?.language ?? "ja") === "ja";

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

const managementNarrative = spec.management_narrative ?? {};
const mainSlideChecks = spec.main_slide_checks ?? {};

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

function addSlideHeader(slide, index, override = null) {
  const specSlide = override ?? slides[index] ?? { title: `Slide ${index + 1}`, message: "" };
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
  const footerLabel = isJa
    ? "出典: out/run_summary_executive.json / out/executive_deck_spec.json"
    : "Source: out/run_summary_executive.json / out/executive_deck_spec.json";
  slide.addText(footerLabel, {
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

function narrativeLabel(key, index = 0) {
  if (key === "conclusion") {
    return isJa ? "結論" : "Conclusion";
  }
  if (key === "rationale") {
    return isJa ? `根拠${index + 1}` : `Rationale ${index + 1}`;
  }
  if (key === "risk") {
    return isJa ? "リスク" : "Risk";
  }
  if (key === "decision_ask") {
    return isJa ? "意思決定要請" : "Decision Ask";
  }
  return key;
}

function getNarrativeBlock(slideId) {
  const block = managementNarrative?.[slideId];
  if (!block || typeof block !== "object") {
    return {
      conclusion: "",
      rationale: [],
      risk: [],
      decision_ask: [],
    };
  }
  return {
    conclusion: String(block.conclusion ?? "").trim(),
    rationale: asStringArray(block.rationale),
    risk: asStringArray(block.risk),
    decision_ask: asStringArray(block.decision_ask),
  };
}

function buildNarrativeLines(slideId, maxLines = 8) {
  const block = getNarrativeBlock(slideId);
  const lines = [];
  if (block.conclusion) {
    lines.push(`${narrativeLabel("conclusion")}: ${block.conclusion}`);
  }
  block.rationale.forEach((text, index) => {
    lines.push(`${narrativeLabel("rationale", index)}: ${text}`);
  });
  block.risk.forEach((text) => {
    lines.push(`${narrativeLabel("risk")}: ${text}`);
  });
  block.decision_ask.forEach((text) => {
    lines.push(`${narrativeLabel("decision_ask")}: ${text}`);
  });
  return lines.slice(0, maxLines);
}

function addNarrativePanel(slide, slideId, options = {}) {
  const x = Number(options.x ?? left);
  const y = Number(options.y ?? 5.3);
  const w = Number(options.w ?? width);
  const h = Number(options.h ?? 1.45);
  const maxLines = Number(options.maxLines ?? 8);
  const lines = buildNarrativeLines(slideId, maxLines);
  const panelTitle = isJa ? "経営説明（結論先出し）" : "Management Narrative";

  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    fill: { color: "FFFFFF" },
    line: { color: colorGrid },
    radius: 0.03,
  });
  trackEditableShape();
  slide.addText(panelTitle, {
    x: x + 0.12,
    y: y + 0.08,
    w: w - 0.24,
    h: 0.22,
    fontFace: fontJa,
    fontSize: bodyPt * 0.58,
    bold: true,
    color: colorPrimary,
  });
  trackEditableShape();
  slide.addText(lines.join("\n"), {
    x: x + 0.12,
    y: y + 0.3,
    w: w - 0.24,
    h: h - 0.38,
    fontFace: fontJa,
    fontSize: bodyPt * 0.52,
    color: colorText,
    breakLine: true,
    valign: "top",
  });
  trackEditableShape();
}

function pickKeyCashflowRows(rows) {
  if (rows.length <= 5) {
    return rows;
  }
  const indexes = [
    0,
    Math.floor(rows.length * 0.25),
    Math.floor(rows.length * 0.5),
    Math.floor(rows.length * 0.75),
    rows.length - 1,
  ];
  const deduped = [...new Set(indexes)];
  return deduped.map((index) => rows[index]);
}

function addExecutiveSummary() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 0);

  slide.addText(spec.headline ?? "", {
    x: left,
    y: 1.25,
    w: width,
    h: 0.52,
    fontFace: fontJa,
    fontSize: subtitlePt * 0.95,
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
      y: 1.9,
      w: cardWidth,
      h: 1.8,
      fill: { color: "FFFFFF" },
      line: { color: colorGrid },
      radius: 0.03,
    });
    trackEditableShape();
    slide.addText(claim.label ?? "", {
      x: cardX + 0.14,
      y: 2.05,
      w: cardWidth - 0.28,
      h: 0.32,
      fontFace: fontJa,
      fontSize: bodyPt * 0.8,
      color: colorSecondary,
    });
    trackEditableShape();
    slide.addText(formatClaimValue(claim), {
      x: cardX + 0.14,
      y: 2.42,
      w: cardWidth - 0.28,
      h: 0.92,
      fontFace: fontEn,
      fontSize: kpiPt * 0.40,
      bold: true,
      color: colorPrimary,
    });
    trackEditableShape();
  }

  const philosophy = asStringArray(spec.pricing_philosophy).slice(0, 2);
  if (philosophy.length > 0) {
    slide.addText(bullets(philosophy), {
      x: left,
      y: 3.8,
      w: width,
      h: 0.9,
      fontFace: fontJa,
      fontSize: bodyPt * 0.6,
      color: colorSecondary,
      breakLine: true,
    });
    trackEditableShape();
  }
  addNarrativePanel(slide, "executive_summary", {
    y: 4.75,
    h: 2.0,
    maxLines: 8,
  });
  addFooter(slide);
}

function addDecisionStatement() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 1);

  const compare = spec.decision_compare ?? {};
  const objectives = compare.objectives ?? {};
  const diff = compare.metric_diff_recommended_minus_counter ?? {};
  const compareReasons = asStringArray(compare.adoption_reason).slice(0, 3);

  slide.addShape(pptx.ShapeType.roundRect, {
    x: left,
    y: 1.45,
    w: width,
    h: 1.25,
    fill: { color: "FFFFFF" },
    line: { color: colorGrid },
    radius: 0.03,
  });
  trackEditableShape();
  slide.addText(
    isJa
      ? `推奨案 objective: ${String(objectives.recommended ?? "-")} / 対向案 objective: ${String(objectives.counter ?? "-")}`
      : `Recommended objective: ${String(objectives.recommended ?? "-")} / Counter objective: ${String(objectives.counter ?? "-")}`,
    {
      x: left + 0.12,
      y: 1.62,
      w: width - 0.24,
      h: 0.3,
      fontFace: fontEn,
      fontSize: bodyPt * 0.62,
      color: colorText,
    }
  );
  trackEditableShape();
  slide.addText(
    isJa
      ? `差分(推奨-対向): min IRR=${Number(diff.min_irr ?? 0).toFixed(6)}, min NBV=${Number(diff.min_nbv ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}, max PTM=${Number(diff.max_premium_to_maturity ?? 0).toFixed(6)}, violations=${Number(diff.violation_count ?? 0).toFixed(0)}`
      : `Delta(rec-counter): min IRR=${Number(diff.min_irr ?? 0).toFixed(6)}, min NBV=${Number(diff.min_nbv ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}, max PTM=${Number(diff.max_premium_to_maturity ?? 0).toFixed(6)}, violations=${Number(diff.violation_count ?? 0).toFixed(0)}`,
    {
      x: left + 0.12,
      y: 1.95,
      w: width - 0.24,
      h: 0.52,
      fontFace: fontEn,
      fontSize: bodyPt * 0.56,
      color: colorSecondary,
      breakLine: true,
    }
  );
  trackEditableShape();

  const reasonRows = [[isJa ? "採否理由" : "Adoption Reason"]];
  compareReasons.forEach((reason) => {
    reasonRows.push([reason]);
  });
  if (reasonRows.length === 1) {
    reasonRows.push([isJa ? "採否理由データなし" : "No adoption reason available"]);
  }
  slide.addTable(reasonRows, {
    x: left,
    y: 2.8,
    w: width,
    h: 1.45,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: "FFFFFF",
    color: colorText,
    fontFace: fontJa,
    fontSize: bodyPt * 0.56,
    autoFit: true,
  });
  trackEditableShape();

  addNarrativePanel(slide, "decision_statement", {
    y: 4.35,
    h: 2.4,
    maxLines: 9,
  });

  slide.addText(
    `main_compare_present=${String(Boolean(mainSlideChecks.main_compare_present))}`,
    {
      x: left,
      y: 6.77,
      w: width,
      h: 0.2,
      fontFace: fontEn,
      fontSize: notePt * 0.9,
      color: colorSecondary,
      align: "left",
    }
  );
  trackEditableShape();
  addFooter(slide);
}

function addPricingRecommendation() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 2);
  const rows = [
    isJa
      ? ["モデルポイント", "年払P", "月払P", "IRR", "NBV", "PTM"]
      : ["model_point", "annual_P", "monthly_P", "IRR", "NBV", "PTM"],
  ];
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
    h: 3.55,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: colorBackground,
    color: colorText,
    fontFace: fontJa,
    fontSize: bodyPt * 0.62,
    autoFit: true,
  });
  trackEditableShape();
  addNarrativePanel(slide, "pricing_recommendation", {
    y: 5.05,
    h: 1.7,
    maxLines: 8,
  });
  addFooter(slide);
}

function addConstraintStatus() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 3);
  const rows = [
    isJa
      ? ["制約", "閾値", "最小ギャップ", "最悪モデル", "判定"]
      : ["constraint", "threshold", "min_gap", "worst_mp", "status"],
  ];
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
    h: 3.2,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: "FFFFFF",
    color: colorText,
    fontFace: fontJa,
    fontSize: bodyPt * 0.60,
  });
  trackEditableShape();
  addNarrativePanel(slide, "constraint_status", {
    y: 4.75,
    h: 2.0,
    maxLines: 8,
  });
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
      { name: isJa ? "保険料" : "Premium", labels, values: premium },
      { name: isJa ? "利差益" : "Investment", labels, values: investment },
      { name: isJa ? "保険金等" : "Benefit", labels, values: benefit },
      { name: isJa ? "事業費" : "Expense", labels, values: expense },
      { name: isJa ? "準備金増減" : "Reserve", labels, values: reserve },
    ],
    {
      x: left,
      y: 1.45,
      w: width,
      h: 3.15,
      barGrouping: "stacked",
      fontFace: fontEn,
      fontSize: bodyPt * 0.56,
      showLegend: true,
      legendPos: "t",
      chartColors: [colorPrimary, colorPositive, colorNegative, colorAccent, colorSecondary],
    }
  );
  trackEditableShape();
  slide.addChart(
    pptx.ChartType.line,
    [{ name: isJa ? "純CF" : "Net CF", labels, values: net }],
    {
      x: left,
      y: 4.62,
      w: width,
      h: 0.52,
      fontFace: fontEn,
      fontSize: bodyPt * 0.52,
      showLegend: false,
      lineSize: 2,
      chartColors: [hexColor("#111111", "111111")],
    }
  );
  trackEditableShape();
  addNarrativePanel(slide, "cashflow_bridge", {
    y: 5.18,
    h: 1.57,
    maxLines: 8,
  });
  addFooter(slide);
}

function addProfitSourceDecomposition() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 5);
  const rows = pickKeyCashflowRows(Array.isArray(spec.cashflow_by_source) ? spec.cashflow_by_source : []);
  const tableRows = [
    isJa
      ? ["年度", "保険料", "利差益", "保険金等", "事業費", "準備金", "純CF"]
      : ["year", "premium", "investment", "benefit", "expense", "reserve", "net_cf"],
  ];
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
    h: 3.8,
    border: { type: "solid", pt: 1, color: colorGrid },
    fontFace: fontJa,
    fontSize: bodyPt * 0.56,
    color: colorText,
    fill: "FFFFFF",
  });
  trackEditableShape();
  addNarrativePanel(slide, "profit_source_decomposition", {
    y: 5.32,
    h: 1.43,
    maxLines: 8,
  });
  addFooter(slide);
}

function addSensitivity() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 6);
  const rows = [
    isJa
      ? ["シナリオ", "min IRR", "min NBV", "max PTM", "違反件数"]
      : ["scenario", "min_irr", "min_nbv", "max_ptm", "violations"],
  ];
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
    h: 3.8,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: "FFFFFF",
    color: colorText,
    fontFace: fontJa,
    fontSize: bodyPt * 0.58,
  });
  trackEditableShape();
  addNarrativePanel(slide, "sensitivity", {
    y: 5.3,
    h: 1.45,
    maxLines: 8,
  });
  addFooter(slide);
}

function addGovernance() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 7);
  const expenseModel = spec.expense_model ?? {};
  const formulaLines = asStringArray(expenseModel.formula_lines).slice(0, 4);

  slide.addShape(pptx.ShapeType.roundRect, {
    x: left,
    y: 1.45,
    w: width,
    h: 2.95,
    fill: { color: "FFFFFF" },
    line: { color: colorGrid },
    radius: 0.03,
  });
  trackEditableShape();
  slide.addText(
    isJa ? "予定事業費の計算式と根拠" : "Planned Expense Formula and Rationale",
    {
      x: left + 0.14,
      y: 1.6,
      w: width - 0.28,
      h: 0.32,
      fontFace: fontJa,
      fontSize: bodyPt * 0.8,
      bold: true,
      color: colorPrimary,
    }
  );
  trackEditableShape();
  slide.addText(bullets(formulaLines), {
    x: left + 0.14,
    y: 1.96,
    w: width - 0.28,
    h: 2.25,
    fontFace: fontEn,
    fontSize: bodyPt * 0.56,
    color: colorText,
    breakLine: true,
  });
  trackEditableShape();
  addNarrativePanel(slide, "governance", {
    y: 4.5,
    h: 2.25,
    maxLines: 8,
  });
  addFooter(slide);
}

function addDecisionAsk() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 8);
  const asks = asStringArray(spec.decision_asks).slice(0, 4);
  slide.addText(bullets(asks), {
    x: left,
    y: 1.5,
    w: width,
    h: 2.05,
    fontFace: fontJa,
    fontSize: bodyPt * 0.68,
    color: colorText,
    breakLine: true,
  });
  trackEditableShape();
  addNarrativePanel(slide, "decision_ask", {
    y: 3.72,
    h: 3.03,
    maxLines: 10,
  });
  addFooter(slide);
}

function addAppendixExpenseFormula() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 8, {
    title: isJa ? "付録A1 予定事業費の式と根拠" : "Appendix A1 Expense Formula",
    message: "Formula Catalog / Source Hash",
  });
  const plannedExpense = spec.formula_catalog?.planned_expense ?? {};
  const formulaLines = asStringArray(plannedExpense.formula_lines);
  const constraints = asStringArray(plannedExpense.constraints);
  const source = plannedExpense.source ?? {};

  slide.addText(bullets(formulaLines), {
    x: left,
    y: 1.45,
    w: width,
    h: 2.6,
    fontFace: fontEn,
    fontSize: bodyPt * 0.62,
    color: colorText,
    breakLine: true,
    valign: "top",
  });
  trackEditableShape();
  slide.addText(bullets(constraints), {
    x: left,
    y: 4.2,
    w: width,
    h: 1.2,
    fontFace: fontEn,
    fontSize: bodyPt * 0.6,
    color: colorSecondary,
    breakLine: true,
  });
  trackEditableShape();
  slide.addText(
    `source_path: ${String(source.path ?? "")}\nsha256: ${String(source.sha256 ?? "")}`,
    {
      x: left,
      y: 5.55,
      w: width,
      h: 1.0,
      fontFace: fontEn,
      fontSize: bodyPt * 0.56,
      color: colorSecondary,
      breakLine: true,
    }
  );
  trackEditableShape();
  addFooter(slide);
}

function addAppendixDecisionCompare() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 8, {
    title: isJa ? "付録A2 2案比較" : "Appendix A2 Decision Compare",
    message: isJa ? "推奨案 vs 対向案" : "Recommended vs Counter",
  });
  const compare = spec.decision_compare ?? {};
  const diff = compare.metric_diff_recommended_minus_counter ?? {};
  const rows = [
    isJa ? ["指標", "推奨-対向"] : ["metric", "recommended-counter"],
    ["min_irr", Number(diff.min_irr ?? 0).toFixed(6)],
    ["min_nbv", Number(diff.min_nbv ?? 0).toLocaleString("en-US", { maximumFractionDigits: 0 })],
    ["min_loading_surplus_ratio", Number(diff.min_loading_surplus_ratio ?? 0).toFixed(6)],
    ["max_premium_to_maturity", Number(diff.max_premium_to_maturity ?? 0).toFixed(6)],
    ["violation_count", Number(diff.violation_count ?? 0).toFixed(0)],
  ];
  slide.addTable(rows, {
    x: left,
    y: 1.45,
    w: width,
    h: 2.2,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: "FFFFFF",
    color: colorText,
    fontFace: fontEn,
    fontSize: bodyPt * 0.58,
  });
  trackEditableShape();

  const priceRows = Array.isArray(compare.price_diff_by_model_point)
    ? compare.price_diff_by_model_point.slice(0, 5)
    : [];
  const tableRows = [
    isJa
      ? ["モデルポイント", "推奨年払P", "対向年払P", "差分(推奨-対向)"]
      : ["model_point", "rec_annual_p", "ctr_annual_p", "delta"],
  ];
  for (const row of priceRows) {
    tableRows.push([
      String(row.model_point),
      Number(row.recommended_annual_premium).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      Number(row.counter_annual_premium).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      Number(row.delta_recommended_minus_counter).toLocaleString("en-US", { maximumFractionDigits: 0 }),
    ]);
  }
  slide.addTable(tableRows, {
    x: left,
    y: 3.85,
    w: width,
    h: 2.2,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: "FFFFFF",
    color: colorText,
    fontFace: fontEn,
    fontSize: bodyPt * 0.56,
  });
  trackEditableShape();
  slide.addText(bullets(compare.adoption_reason ?? []), {
    x: left,
    y: 6.15,
    w: width,
    h: 0.7,
    fontFace: fontJa,
    fontSize: bodyPt * 0.54,
    color: colorSecondary,
    breakLine: true,
  });
  trackEditableShape();
  addFooter(slide);
}

function addAppendixCausalBridge() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 8, {
    title: isJa ? "付録A3 橋渡し分解" : "Appendix A3 Causal Bridge",
    message: isJa ? "P差分から利源別寄与へ" : "Premium gap to profit source contribution",
  });
  const causalBridge = spec.causal_bridge ?? {};
  const components = Array.isArray(causalBridge.components) ? causalBridge.components : [];
  const rows = [
    isJa
      ? ["要素", "推奨案合計", "対向案合計", "差分(推奨-対向)", "寄与率"]
      : ["component", "recommended", "counter", "delta", "ratio"],
  ];
  for (const row of components) {
    rows.push([
      String(row.label ?? row.component),
      Number(row.recommended_total).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      Number(row.counter_total).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      Number(row.delta_recommended_minus_counter).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      `${(Number(row.contribution_ratio_to_net_delta) * 100).toFixed(1)}%`,
    ]);
  }
  slide.addTable(rows, {
    x: left,
    y: 1.45,
    w: width,
    h: 5.1,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: "FFFFFF",
    color: colorText,
    fontFace: fontEn,
    fontSize: bodyPt * 0.54,
  });
  trackEditableShape();
  addFooter(slide);
}

function addAppendixSensitivityDecomposition() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 8, {
    title: isJa ? "付録A4 感応度分解" : "Appendix A4 Sensitivity Decomposition",
    message: isJa ? "支配シナリオ順位" : "Dominant scenario ranking",
  });
  const decomp = spec.sensitivity_decomposition ?? {};
  const recRows = Array.isArray(decomp.recommended) ? decomp.recommended.slice(0, 5) : [];
  const rows = [
    isJa
      ? ["シナリオ", "Δmin_irr", "Δmin_nbv", "Δmax_ptm", "Δ違反件数", "risk_score"]
      : ["scenario", "d_min_irr", "d_min_nbv", "d_max_ptm", "d_violations", "risk_score"],
  ];
  for (const row of recRows) {
    rows.push([
      String(row.scenario),
      Number(row.delta_min_irr).toFixed(6),
      Number(row.delta_min_nbv).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      Number(row.delta_max_ptm).toFixed(6),
      Number(row.delta_violation_count).toFixed(0),
      Number(row.risk_score).toFixed(4),
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
    fontSize: bodyPt * 0.56,
  });
  trackEditableShape();
  addFooter(slide);
}

function addAppendixProCon() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 8, {
    title: isJa ? "付録A5 Pro/Con" : "Appendix A5 Pro/Con",
    message: isJa ? "定量3 + 定性3" : "Quant 3 + Qual 3",
  });
  const procon = spec.procon ?? {};
  const rec = procon.recommended ?? {};
  const prosQuant = Array.isArray(rec.pros?.quant) ? rec.pros.quant : [];
  const prosQual = Array.isArray(rec.pros?.qual) ? rec.pros.qual : [];
  const consQuant = Array.isArray(rec.cons?.quant) ? rec.cons.quant : [];
  const consQual = Array.isArray(rec.cons?.qual) ? rec.cons.qual : [];

  slide.addText("Pros", {
    x: left,
    y: 1.45,
    w: width / 2 - 0.05,
    h: 0.3,
    fontFace: fontEn,
    fontSize: bodyPt * 0.8,
    bold: true,
    color: colorPositive,
  });
  trackEditableShape();
  slide.addText(
    bullets([...prosQuant.slice(0, 3).map((x) => x.text), ...prosQual.slice(0, 3).map((x) => x.text)]),
    {
      x: left,
      y: 1.8,
      w: width / 2 - 0.05,
      h: 4.8,
      fontFace: fontJa,
      fontSize: bodyPt * 0.53,
      color: colorText,
      breakLine: true,
      valign: "top",
    }
  );
  trackEditableShape();
  slide.addText("Cons", {
    x: left + width / 2 + 0.05,
    y: 1.45,
    w: width / 2 - 0.05,
    h: 0.3,
    fontFace: fontEn,
    fontSize: bodyPt * 0.8,
    bold: true,
    color: colorNegative,
  });
  trackEditableShape();
  slide.addText(
    bullets([...consQuant.slice(0, 3).map((x) => x.text), ...consQual.slice(0, 3).map((x) => x.text)]),
    {
      x: left + width / 2 + 0.05,
      y: 1.8,
      w: width / 2 - 0.05,
      h: 4.8,
      fontFace: fontJa,
      fontSize: bodyPt * 0.53,
      color: colorText,
      breakLine: true,
      valign: "top",
    }
  );
  trackEditableShape();
  addFooter(slide);
}

function addAppendixAuditTrail() {
  const slide = pptx.addSlide();
  addSlideHeader(slide, 8, {
    title: isJa ? "付録A6 監査証跡" : "Appendix A6 Audit Trail",
    message: "trace_map + formula IDs",
  });
  const trace = Array.isArray(spec.trace_map) ? spec.trace_map.slice(0, 10) : [];
  const rows = [["claim_id", "source_file", "source_path"]];
  for (const row of trace) {
    rows.push([
      String(row.claim_id ?? ""),
      String(row.source_file ?? ""),
      String(row.source_path ?? ""),
    ]);
  }
  slide.addTable(rows, {
    x: left,
    y: 1.45,
    w: width,
    h: 4.5,
    border: { type: "solid", pt: 1, color: colorGrid },
    fill: "FFFFFF",
    color: colorText,
    fontFace: fontEn,
    fontSize: bodyPt * 0.53,
  });
  trackEditableShape();
  const formulaId = spec.formula_catalog?.planned_expense?.id ?? "";
  slide.addText(`formula_id: ${String(formulaId)}`, {
    x: left,
    y: 6.05,
    w: width,
    h: 0.55,
    fontFace: fontEn,
    fontSize: bodyPt * 0.56,
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
addAppendixExpenseFormula();
addAppendixDecisionCompare();
addAppendixCausalBridge();
addAppendixSensitivityDecomposition();
addAppendixProCon();
addAppendixAuditTrail();

fs.mkdirSync(path.dirname(outPath), { recursive: true });
await pptx.writeFile({ fileName: outPath });

counts.slide_count = 15;
fs.mkdirSync(path.dirname(metricsOutPath), { recursive: true });
fs.writeFileSync(metricsOutPath, JSON.stringify(counts, null, 2), "utf8");
