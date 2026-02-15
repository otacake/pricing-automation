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

function asStringArray(value) {
  return (Array.isArray(value) ? value : [])
    .map((item) => String(item).trim())
    .filter((item) => item.length > 0);
}

function asNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function hexColor(value, fallback) {
  if (typeof value !== "string" || value.trim() === "") {
    return fallback;
  }
  return value.replace("#", "").toUpperCase();
}

function formatPct(value, digits = 2) {
  return `${(asNumber(value, 0) * 100).toFixed(digits)}%`;
}

function formatRatio(value, digits = 4) {
  return asNumber(value, 0).toFixed(digits);
}

function formatCurrency(value) {
  return `JPY ${asNumber(value, 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function formatClaimValue(item) {
  const value = asNumber(item?.value, 0);
  switch (item?.format) {
    case "pct":
      return `${(value * 100).toFixed(2)}%`;
    case "currency_jpy":
      return `JPY ${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
    case "ratio":
      return value.toFixed(4);
    case "integer":
      return `${Math.round(value)}`;
    default:
      return `${item?.value ?? "-"}`;
  }
}

function shortenModelPoint(label) {
  const text = String(label ?? "").trim();
  if (text.length <= 12) {
    return text;
  }
  const parts = text.split("_").filter(Boolean);
  if (parts.length >= 3) {
    return `${parts[0].slice(0, 1).toUpperCase()}${parts[1].replace("age", "A")}${parts[2].replace("term", "T")}`;
  }
  return text.slice(0, 12);
}

function bullets(lines) {
  const items = asStringArray(lines);
  return items.length > 0 ? items.map((line) => `- ${line}`).join("\n") : "-";
}

function pickRows(rows, count = 6) {
  if (!Array.isArray(rows) || rows.length <= count) {
    return Array.isArray(rows) ? rows : [];
  }
  const picks = [
    0,
    Math.floor(rows.length * 0.2),
    Math.floor(rows.length * 0.4),
    Math.floor(rows.length * 0.6),
    Math.floor(rows.length * 0.8),
    rows.length - 1,
  ];
  const unique = [...new Set(picks)];
  return unique.map((index) => rows[index]);
}

const args = parseArgs(process.argv);
const specPath = requireArg(args, "spec");
const outPath = requireArg(args, "out");
const metricsOutPath = requireArg(args, "metrics-out");

const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const style = spec?.style ?? {};
const colors = style?.colors ?? {};
const fonts = style?.fonts ?? {};
const typography = style?.typography ?? {};
const layout = style?.layout ?? {};
const tableRendering = spec?.table_rendering ?? style?.tables ?? {};
const chartRendering = spec?.chart_rendering ?? style?.charts ?? {};
const narrativeContract = style?.narrative ?? {};

const slideDefs = Array.isArray(spec?.slides) ? spec.slides : [];
const slideMetaRows = Array.isArray(spec?.slide_meta) ? spec.slide_meta : [];
const slideDefById = new Map(slideDefs.map((row) => [String(row.id), row]));
const slideMetaById = new Map(slideMetaRows.map((row) => [String(row.slide_id), row]));

const isJa = (spec?.meta?.language ?? "ja") === "ja";
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
const titlePt = asNumber(typography.title_pt, 34);
const subtitlePt = asNumber(typography.subtitle_pt, 18);
const bodyPt = asNumber(typography.body_pt, 16);
const notePt = asNumber(typography.note_pt, 11);
const kpiPt = asNumber(typography.kpi_pt, 44);

const slideSize = layout.slide_size_in ?? { width: 13.333, height: 7.5 };
const margins = layout.margins_in ?? { left: 0.6, right: 0.6, top: 0.35, bottom: 0.3 };
const slideWidth = asNumber(slideSize.width, 13.333);
const slideHeight = asNumber(slideSize.height, 7.5);
const marginLeft = asNumber(margins.left, 0.6);
const marginRight = asNumber(margins.right, 0.6);
const contentWidth = slideWidth - marginLeft - marginRight;
const headerHeight = 0.92;
const bodyTop = headerHeight + 0.2;
const footerLineY = slideHeight - 0.34;
const footerTextY = slideHeight - 0.27;

const tableDefaults = {
  border: { type: "solid", pt: 1, color: colorGrid },
  color: colorText,
  fontFace: fontJa,
  fontSize: bodyPt * 0.56,
  autoPage: Boolean(tableRendering.auto_page_default ?? true),
  autoPageRepeatHeader: Boolean(tableRendering.auto_page_repeat_header ?? true),
  autoPageHeaderRows: asNumber(tableRendering.auto_page_header_rows, 1),
  autoPageSlideStartY: asNumber(tableRendering.auto_page_slide_start_y, bodyTop),
};

const showValueLabels = Boolean(chartRendering.value_label_default ?? true);
const valueLabelFormat = String(chartRendering.value_label_format_code ?? "#,##0");
const lineValueLabelFormat = String(chartRendering.line_value_label_format_code ?? "#,##0");

const metrics = {
  total_shape_count: 0,
  editable_shape_count: 0,
  alt_text_total: 0,
  alt_text_present: 0,
  speaker_notes_total: 0,
  speaker_notes_present: 0,
  table_overflow_ok: true,
  slide_count: 0,
};

function trackEditable() {
  metrics.total_shape_count += 1;
  metrics.editable_shape_count += 1;
}

function trackAltText(altText) {
  metrics.alt_text_total += 1;
  if (typeof altText === "string" && altText.trim()) {
    metrics.alt_text_present += 1;
  }
}

function addImageTracked(slide, options, altText) {
  trackAltText(altText);
  slide.addImage({ ...options, altText });
  trackEditable();
}

function addChartTracked(slide, type, data, options, altText) {
  trackAltText(altText);
  slide.addChart(type, data, { ...options, altText });
  trackEditable();
}

function addTableTracked(slide, rows, options = {}) {
  const merged = { ...tableDefaults, ...options };
  if (!Array.isArray(rows) || rows.length <= 1) {
    merged.autoPage = false;
  }
  slide.addTable(rows, merged);
  trackEditable();
  const rowCount = Array.isArray(rows) ? rows.length : 0;
  if (rowCount > 12 && !merged.autoPage) {
    metrics.table_overflow_ok = false;
  }
}

function narrativeLabel(section, index = 0) {
  if (section === "conclusion") {
    return isJa ? "結論" : "Conclusion";
  }
  if (section === "rationale") {
    return isJa ? `根拠${index + 1}` : `Rationale ${index + 1}`;
  }
  if (section === "risk") {
    return isJa ? "リスク" : "Risk";
  }
  if (section === "decision_ask") {
    return isJa ? "意思決定要請" : "Decision Ask";
  }
  return section;
}

function getNarrativeBlock(slideId) {
  const raw = spec?.management_narrative?.[slideId];
  if (!raw || typeof raw !== "object") {
    return {
      conclusion: "",
      rationale: [],
      risk: [],
      decision_ask: [],
    };
  }
  return {
    conclusion: String(raw.conclusion ?? "").trim(),
    rationale: asStringArray(raw.rationale),
    risk: asStringArray(raw.risk),
    decision_ask: asStringArray(raw.decision_ask),
  };
}

function buildNarrativeLines(slideId, maxLines = 8) {
  const block = getNarrativeBlock(slideId);
  const lines = [];
  if (block.conclusion) {
    lines.push(`${narrativeLabel("conclusion")}: ${block.conclusion}`);
  }
  block.rationale.forEach((item, index) => {
    lines.push(`${narrativeLabel("rationale", index)}: ${item}`);
  });
  block.risk.forEach((item) => {
    lines.push(`${narrativeLabel("risk")}: ${item}`);
  });
  block.decision_ask.forEach((item) => {
    lines.push(`${narrativeLabel("decision_ask")}: ${item}`);
  });
  return lines.slice(0, maxLines);
}

function addNarrativePanel(slide, slideId, options = {}) {
  const x = asNumber(options.x, marginLeft);
  const y = asNumber(options.y, 5.12);
  const w = asNumber(options.w, contentWidth);
  const h = asNumber(options.h, 1.92);
  const maxLines = asNumber(options.maxLines, 9);
  const lines = buildNarrativeLines(slideId, maxLines);

  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    fill: { color: "FFFFFF" },
    line: { color: colorGrid, pt: 1 },
    radius: 0.03,
  });
  trackEditable();

  slide.addText(isJa ? "経営説明（結論先出し）" : "Management Narrative (Conclusion First)", {
    x: x + 0.12,
    y: y + 0.07,
    w: w - 0.24,
    h: 0.2,
    fontFace: fontJa,
    fontSize: bodyPt * 0.56,
    bold: true,
    color: colorPrimary,
  });
  trackEditable();

  slide.addText(lines.length > 0 ? lines.join("\n") : "-", {
    x: x + 0.12,
    y: y + 0.28,
    w: w - 0.24,
    h: h - 0.36,
    fontFace: fontJa,
    fontSize: bodyPt * 0.51,
    color: colorText,
    valign: "top",
    breakLine: true,
  });
  trackEditable();
}

const scriptDir = path.dirname(process.argv[1]);
const iconDir = path.resolve(scriptDir, "..", "assets", "icons");

function resolveIcon(slideId) {
  const direct = path.join(iconDir, `${slideId}.svg`);
  if (fs.existsSync(direct)) {
    return direct;
  }
  const fallback = path.join(iconDir, "generic.svg");
  return fs.existsSync(fallback) ? fallback : null;
}

const pptx = new pptxgen();
pptx.defineLayout({ name: "CUSTOM", width: slideWidth, height: slideHeight });
pptx.layout = "CUSTOM";
pptx.author = "pricing-automation";
pptx.company = "pricing-automation";
pptx.subject = "Executive pricing deck";
pptx.title = "Executive pricing deck";

const footerSource = "Source: out/run_summary_executive.json / out/executive_deck_spec.json";

pptx.defineSlideMaster({
  title: "main_master",
  background: { color: colorBackground },
  slideNumber: {
    x: slideWidth - marginRight - 0.35,
    y: footerTextY,
    w: 0.3,
    h: 0.16,
    fontFace: fontEn,
    fontSize: notePt * 0.76,
    color: colorSecondary,
    align: "right",
  },
  objects: [
    { rect: { x: 0, y: 0, w: slideWidth, h: headerHeight, fill: { color: colorPrimary }, line: { color: colorPrimary } } },
    { line: { x: marginLeft, y: footerLineY, w: contentWidth, h: 0, line: { color: colorGrid, pt: 1 } } },
    { text: { text: footerSource, options: { x: marginLeft, y: footerTextY, w: contentWidth - 0.4, h: 0.16, fontFace: fontEn, fontSize: notePt * 0.74, color: colorSecondary, align: "left" } } },
  ],
});

pptx.defineSlideMaster({
  title: "appendix_master",
  background: { color: "FFFFFF" },
  slideNumber: {
    x: slideWidth - marginRight - 0.35,
    y: footerTextY,
    w: 0.3,
    h: 0.16,
    fontFace: fontEn,
    fontSize: notePt * 0.74,
    color: colorSecondary,
    align: "right",
  },
  objects: [
    { rect: { x: 0, y: 0, w: slideWidth, h: headerHeight, fill: { color: colorSecondary }, line: { color: colorSecondary } } },
    { line: { x: marginLeft, y: footerLineY, w: contentWidth, h: 0, line: { color: colorGrid, pt: 1 } } },
    { text: { text: footerSource, options: { x: marginLeft, y: footerTextY, w: contentWidth - 0.4, h: 0.16, fontFace: fontEn, fontSize: notePt * 0.74, color: colorSecondary, align: "left" } } },
  ],
});

let createdSlideCount = 0;

function addSlideIcon(slide, slideId) {
  const iconPath = resolveIcon(slideId);
  if (!iconPath) {
    return;
  }
  addImageTracked(
    slide,
    {
      path: iconPath,
      x: marginLeft + contentWidth - 0.48,
      y: 0.16,
      w: 0.3,
      h: 0.3,
    },
    `${slideId} icon`
  );
}

function resolveSlideHeader(slideId, override = {}) {
  const def = slideDefById.get(slideId) ?? {};
  const meta = slideMetaById.get(slideId) ?? {};
  const title = String(override.title ?? def.title ?? meta.title ?? slideId);
  const message = String(override.message ?? def.message ?? "");
  return { title, message };
}

function createSlide(slideId, options = {}) {
  const meta = slideMetaById.get(slideId) ?? {};
  const masterName = String(options.masterName ?? meta.master ?? "main_master");
  const slide = pptx.addSlide({ masterName });
  createdSlideCount += 1;

  const { title, message } = resolveSlideHeader(slideId, options);
  slide.addText(title, {
    x: marginLeft + 0.16,
    y: 0.14,
    w: contentWidth - 0.64,
    h: 0.3,
    fontFace: fontEn,
    fontSize: titlePt * 0.4,
    bold: true,
    color: "FFFFFF",
  });
  trackEditable();

  if (message) {
    slide.addText(message, {
      x: marginLeft + 0.16,
      y: 0.5,
      w: contentWidth - 0.64,
      h: 0.24,
      fontFace: fontJa,
      fontSize: subtitlePt * 0.58,
      color: "FFFFFF",
      breakLine: true,
    });
    trackEditable();
  }

  if (masterName === "main_master") {
    addSlideIcon(slide, slideId);
    if (String(narrativeContract.notes_mode ?? "auto_from_narrative") === "auto_from_narrative") {
      metrics.speaker_notes_total += 1;
      const notes = String(meta.speaker_notes ?? "").trim();
      if (notes) {
        slide.addNotes(notes);
        metrics.speaker_notes_present += 1;
      }
    }
  }

  return slide;
}

function addExecutiveSummarySlide() {
  const slide = createSlide("executive_summary");

  slide.addText(String(spec.headline ?? ""), {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 0.45,
    fontFace: fontJa,
    fontSize: subtitlePt * 0.88,
    bold: true,
    color: colorText,
    breakLine: true,
  });
  trackEditable();

  const claims = Array.isArray(spec.summary_claims) ? spec.summary_claims : [];
  const gap = 0.14;
  const cardCount = Math.max(claims.length, 1);
  const cardWidth = (contentWidth - gap * (cardCount - 1)) / cardCount;
  for (let index = 0; index < claims.length; index += 1) {
    const card = claims[index];
    const x = marginLeft + index * (cardWidth + gap);
    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y: bodyTop + 0.58,
      w: cardWidth,
      h: 1.56,
      fill: { color: "FFFFFF" },
      line: { color: colorGrid, pt: 1 },
      radius: 0.03,
    });
    trackEditable();

    slide.addText(String(card.label ?? ""), {
      x: x + 0.12,
      y: bodyTop + 0.72,
      w: cardWidth - 0.24,
      h: 0.26,
      fontFace: fontJa,
      fontSize: bodyPt * 0.64,
      color: colorSecondary,
    });
    trackEditable();

    slide.addText(formatClaimValue(card), {
      x: x + 0.12,
      y: bodyTop + 1.0,
      w: cardWidth - 0.24,
      h: 0.82,
      fontFace: fontEn,
      fontSize: kpiPt * 0.35,
      color: colorPrimary,
      bold: true,
    });
    trackEditable();
  }

  slide.addText(bullets(asStringArray(spec.pricing_philosophy).slice(0, 3)), {
    x: marginLeft,
    y: bodyTop + 2.28,
    w: contentWidth,
    h: 1.0,
    fontFace: fontJa,
    fontSize: bodyPt * 0.54,
    color: colorSecondary,
    breakLine: true,
    valign: "top",
  });
  trackEditable();

  addNarrativePanel(slide, "executive_summary", { y: 4.66, h: 2.1, maxLines: 10 });
}

function metricSummaryRows(alt) {
  const metricsMap = alt?.metrics ?? {};
  return [
    ["min IRR", formatPct(metricsMap.min_irr, 2)],
    ["min NBV", formatCurrency(metricsMap.min_nbv)],
    ["max PTM", formatRatio(metricsMap.max_premium_to_maturity, 4)],
    ["violations", `${Math.round(asNumber(metricsMap.violation_count, 0))}`],
  ];
}

function addAlternativeCard(slide, label, alt, x, y, w) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h: 1.45,
    fill: { color: "FFFFFF" },
    line: { color: colorGrid, pt: 1 },
    radius: 0.03,
  });
  trackEditable();

  slide.addText(label, {
    x: x + 0.1,
    y: y + 0.08,
    w: w - 0.2,
    h: 0.2,
    fontFace: fontJa,
    fontSize: bodyPt * 0.62,
    color: colorPrimary,
    bold: true,
  });
  trackEditable();

  const rows = [["Metric", "Value"], ...metricSummaryRows(alt)];
  addTableTracked(slide, rows, {
    x: x + 0.1,
    y: y + 0.3,
    w: w - 0.2,
    h: 1.05,
    fontFace: fontEn,
    fontSize: bodyPt * 0.5,
    fill: "FFFFFF",
    autoPage: false,
  });
}

function addDecisionStatementSlide() {
  const slide = createSlide("decision_statement");
  const compare = spec?.decision_compare ?? {};
  const alternatives = spec?.alternatives ?? {};
  const reasons = asStringArray(compare.adoption_reason).slice(0, 3);

  const topY = bodyTop;
  const cardGap = 0.16;
  const cardWidth = (contentWidth - cardGap) / 2;
  addAlternativeCard(slide, isJa ? "推奨案" : "Recommended", alternatives?.recommended ?? {}, marginLeft, topY, cardWidth);
  addAlternativeCard(slide, isJa ? "対向案" : "Counter", alternatives?.counter ?? {}, marginLeft + cardWidth + cardGap, topY, cardWidth);

  const priceDiffRows = Array.isArray(compare.price_diff_by_model_point) ? compare.price_diff_by_model_point.slice(0, 8) : [];
  const labels = priceDiffRows.map((row) => shortenModelPoint(row.model_point));
  const deltaSeries = priceDiffRows.map((row) => asNumber(row.delta_recommended_minus_counter, 0));
  let running = 0;
  const cumulative = deltaSeries.map((value) => {
    running += value;
    return running;
  });

  addChartTracked(
    slide,
    pptx.ChartType.bar,
    [{ name: isJa ? "年間保険料差分" : "Annual Premium Delta", labels, values: deltaSeries }],
    {
      x: marginLeft,
      y: topY + 1.56,
      w: contentWidth,
      h: 1.55,
      chartColors: [colorAccent],
      showLegend: false,
      catAxisLabelRotate: 315,
      valAxisNumFmtCode: valueLabelFormat,
      showValue: showValueLabels,
      dataLabelFormatCode: valueLabelFormat,
      fontFace: fontEn,
      fontSize: bodyPt * 0.48,
    },
    "Decision statement bar chart: premium delta by model point"
  );

  if (labels.length > 0) {
    addChartTracked(
      slide,
      pptx.ChartType.line,
      [{ name: isJa ? "累積差分" : "Cumulative Delta", labels, values: cumulative }],
      {
        x: marginLeft,
        y: topY + 3.14,
        w: contentWidth,
        h: 0.62,
        chartColors: [colorPrimary],
        showLegend: false,
        lineSize: 2,
        valAxisNumFmtCode: lineValueLabelFormat,
        showValue: showValueLabels,
        dataLabelFormatCode: lineValueLabelFormat,
        fontFace: fontEn,
        fontSize: bodyPt * 0.46,
      },
      "Decision statement line chart: cumulative premium delta"
    );
  }

  slide.addText(
    reasons.length > 0 ? reasons.map((item, index) => `${index + 1}. ${item}`).join("\n") : "-",
    {
      x: marginLeft,
      y: topY + 3.82,
      w: contentWidth,
      h: 0.78,
      fontFace: fontJa,
      fontSize: bodyPt * 0.52,
      color: colorSecondary,
      breakLine: true,
      valign: "top",
    }
  );
  trackEditable();

  addNarrativePanel(slide, "decision_statement", { y: 4.66, h: 2.1, maxLines: 10 });
}

function addPricingRecommendationSlide() {
  const slide = createSlide("pricing_recommendation");
  const rows = [["Model Point", "Annual P", "Monthly P", "IRR", "NBV", "PTM"]];
  const pricingRows = Array.isArray(spec.pricing_table) ? spec.pricing_table : [];
  pricingRows.forEach((row) => {
    rows.push([
      String(row.model_point ?? ""),
      asNumber(row.gross_annual_premium, 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      asNumber(row.monthly_premium, 0).toLocaleString("en-US", { maximumFractionDigits: 1 }),
      formatPct(row.irr),
      asNumber(row.nbv, 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      formatRatio(row.premium_to_maturity, 4),
    ]);
  });
  addTableTracked(slide, rows, {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 3.75,
    fill: "FFFFFF",
    masterSlideName: "main_master",
  });
  addNarrativePanel(slide, "pricing_recommendation", { y: 4.66, h: 2.1, maxLines: 9 });
}

function addConstraintStatusSlide() {
  const slide = createSlide("constraint_status");
  const rows = [["Constraint", "Threshold", "Min Gap", "Worst Model Point", "Status"]];
  const constraints = Array.isArray(spec.constraint_status) ? spec.constraint_status : [];
  constraints.forEach((row) => {
    rows.push([
      String(row.label ?? row.constraint ?? ""),
      asNumber(row.threshold, 0).toLocaleString("en-US", { maximumFractionDigits: 6 }),
      asNumber(row.min_gap, 0).toLocaleString("en-US", { maximumFractionDigits: 6 }),
      String(row.worst_model_point ?? ""),
      row.all_ok ? "OK" : "NG",
    ]);
  });
  addTableTracked(slide, rows, {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 3.55,
    fill: "FFFFFF",
    masterSlideName: "main_master",
  });
  addNarrativePanel(slide, "constraint_status", { y: 4.66, h: 2.1, maxLines: 9 });
}

function addCashflowBridgeSlide() {
  const slide = createSlide("cashflow_bridge");
  const rows = Array.isArray(spec.cashflow_by_source) ? spec.cashflow_by_source : [];
  const labels = rows.map((row) => `Y${row.year}`);

  addChartTracked(
    slide,
    pptx.ChartType.bar,
    [
      { name: "Premium", labels, values: rows.map((row) => asNumber(row.premium_income, 0)) },
      { name: "Investment", labels, values: rows.map((row) => asNumber(row.investment_income, 0)) },
      { name: "Benefit", labels, values: rows.map((row) => asNumber(row.benefit_outgo, 0)) },
      { name: "Expense", labels, values: rows.map((row) => asNumber(row.expense_outgo, 0)) },
      { name: "Reserve", labels, values: rows.map((row) => asNumber(row.reserve_change_outgo, 0)) },
    ],
    {
      x: marginLeft,
      y: bodyTop,
      w: contentWidth,
      h: 2.98,
      barGrouping: "stacked",
      showLegend: true,
      legendPos: "t",
      chartColors: [colorPrimary, colorPositive, colorNegative, colorAccent, colorSecondary],
      showValue: showValueLabels,
      dataLabelFormatCode: valueLabelFormat,
      valAxisNumFmtCode: valueLabelFormat,
      fontFace: fontEn,
      fontSize: bodyPt * 0.5,
    },
    "Cashflow bridge stacked chart by profit source"
  );

  addChartTracked(
    slide,
    pptx.ChartType.line,
    [{ name: "Net CF", labels, values: rows.map((row) => asNumber(row.net_cf, 0)) }],
    {
      x: marginLeft,
      y: bodyTop + 3.02,
      w: contentWidth,
      h: 1.12,
      showLegend: false,
      lineSize: 2,
      chartColors: [colorText],
      showValue: showValueLabels,
      dataLabelFormatCode: lineValueLabelFormat,
      valAxisNumFmtCode: lineValueLabelFormat,
      fontFace: fontEn,
      fontSize: bodyPt * 0.48,
    },
    "Cashflow bridge line chart for net cashflow"
  );

  addNarrativePanel(slide, "cashflow_bridge", { y: 5.16, h: 1.6, maxLines: 8 });
}

function addProfitSourceDecompositionSlide() {
  const slide = createSlide("profit_source_decomposition");
  const sampled = pickRows(Array.isArray(spec.cashflow_by_source) ? spec.cashflow_by_source : [], 6);
  const tableRows = [["Year", "Premium", "Investment", "Benefit", "Expense", "Reserve", "Net CF"]];
  sampled.forEach((row) => {
    tableRows.push([
      `Y${row.year}`,
      formatCurrency(row.premium_income),
      formatCurrency(row.investment_income),
      formatCurrency(row.benefit_outgo),
      formatCurrency(row.expense_outgo),
      formatCurrency(row.reserve_change_outgo),
      formatCurrency(row.net_cf),
    ]);
  });

  addTableTracked(slide, tableRows, {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 3.7,
    fill: "FFFFFF",
    autoPage: false,
  });

  const causalComponents = Array.isArray(spec?.causal_bridge?.components)
    ? spec.causal_bridge.components.filter((row) => String(row.component ?? row.label ?? "") !== "net_cf")
    : [];
  const labels = causalComponents.slice(0, 6).map((row) => String(row.label ?? row.component ?? ""));
  const values = causalComponents.slice(0, 6).map((row) => asNumber(row.delta_recommended_minus_counter, 0));

  if (labels.length > 0) {
    addChartTracked(
      slide,
      pptx.ChartType.bar,
      [{ name: isJa ? "案差分寄与" : "Contribution Delta", labels, values }],
      {
        x: marginLeft,
        y: bodyTop + 3.75,
        w: contentWidth,
        h: 1.3,
        showLegend: false,
        chartColors: [colorPrimary],
        showValue: showValueLabels,
        dataLabelFormatCode: valueLabelFormat,
        valAxisNumFmtCode: valueLabelFormat,
        fontFace: fontEn,
        fontSize: bodyPt * 0.46,
      },
      "Profit source decomposition contribution chart"
    );
  }

  addNarrativePanel(slide, "profit_source_decomposition", { y: 5.16, h: 1.6, maxLines: 8 });
}

function addSensitivitySlide() {
  const slide = createSlide("sensitivity");
  const rows = [["Scenario", "Min IRR", "Min NBV", "Max PTM", "Violations"]];
  const sensitivityRows = Array.isArray(spec.sensitivity) ? spec.sensitivity : [];
  sensitivityRows.forEach((row) => {
    rows.push([
      String(row.scenario ?? ""),
      formatPct(row.min_irr),
      formatCurrency(row.min_nbv),
      formatRatio(row.max_premium_to_maturity, 4),
      `${Math.round(asNumber(row.violation_count, 0))}`,
    ]);
  });

  addTableTracked(slide, rows, {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 3.75,
    fill: "FFFFFF",
    masterSlideName: "main_master",
  });

  const dominant = Array.isArray(spec?.sensitivity_decomposition?.recommended)
    ? spec.sensitivity_decomposition.recommended.slice(0, 3).map((row) => String(row.scenario ?? ""))
    : [];
  if (dominant.length > 0) {
    slide.addText(`${isJa ? "支配シナリオ" : "Dominant scenarios"}: ${dominant.join(", ")}`, {
      x: marginLeft,
      y: bodyTop + 3.82,
      w: contentWidth,
      h: 0.28,
      fontFace: fontJa,
      fontSize: bodyPt * 0.5,
      color: colorSecondary,
    });
    trackEditable();
  }

  addNarrativePanel(slide, "sensitivity", { y: 4.66, h: 2.1, maxLines: 9 });
}

function addGovernanceSlide() {
  const slide = createSlide("governance");
  const expenseModel = spec.expense_model ?? {};
  const formulaLines = asStringArray(expenseModel.formula_lines);
  const rationaleLines = asStringArray(expenseModel.rationale_lines);

  slide.addShape(pptx.ShapeType.roundRect, {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 2.55,
    fill: { color: "FFFFFF" },
    line: { color: colorGrid, pt: 1 },
    radius: 0.03,
  });
  trackEditable();

  slide.addText(isJa ? "予定事業費の式と根拠" : "Planned expense formulas and rationale", {
    x: marginLeft + 0.12,
    y: bodyTop + 0.08,
    w: contentWidth - 0.24,
    h: 0.24,
    fontFace: fontJa,
    fontSize: bodyPt * 0.62,
    bold: true,
    color: colorPrimary,
  });
  trackEditable();

  slide.addText(bullets([...formulaLines, ...rationaleLines.slice(0, 2)]), {
    x: marginLeft + 0.12,
    y: bodyTop + 0.34,
    w: contentWidth - 0.24,
    h: 2.08,
    fontFace: fontEn,
    fontSize: bodyPt * 0.5,
    color: colorText,
    breakLine: true,
  });
  trackEditable();

  const formulaSource = spec?.formula_catalog?.planned_expense?.source ?? {};
  slide.addText(
    `source_path: ${String(formulaSource.path ?? "-")}\nsha256: ${String(formulaSource.sha256 ?? "-")}`,
    {
      x: marginLeft,
      y: bodyTop + 2.65,
      w: contentWidth,
      h: 0.62,
      fontFace: fontEn,
      fontSize: bodyPt * 0.46,
      color: colorSecondary,
      breakLine: true,
    }
  );
  trackEditable();

  addNarrativePanel(slide, "governance", { y: 4.66, h: 2.1, maxLines: 9 });
}

function addDecisionAskSlide() {
  const slide = createSlide("decision_ask");
  const asks = asStringArray(spec.decision_asks).slice(0, 6);

  slide.addText(bullets(asks), {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 2.4,
    fontFace: fontJa,
    fontSize: bodyPt * 0.58,
    color: colorText,
    breakLine: true,
  });
  trackEditable();

  const actionRows = [
    ["Workstream", "Owner", "Trigger"],
    ["Pricing Deployment", "Pricing Lead", "Board approval"],
    ["Constraint Monitoring", "Actuarial", "Monthly KPI check"],
    ["Stress Re-run", "Risk", "min IRR < 2.0% or max PTM > 1.056"],
  ];
  addTableTracked(slide, actionRows, {
    x: marginLeft,
    y: bodyTop + 2.46,
    w: contentWidth,
    h: 1.72,
    fill: "FFFFFF",
    autoPage: false,
  });

  addNarrativePanel(slide, "decision_ask", { y: 4.66, h: 2.1, maxLines: 9 });
}

function addAppendixA1() {
  const slide = createSlide("appendix_a1_expense_formula", {
    masterName: "appendix_master",
    title: isJa ? "付録 A1 予定事業費の式と根拠" : "Appendix A1 Expense Formula",
    message: "Formula catalog and source trace",
  });

  const planned = spec?.formula_catalog?.planned_expense ?? {};
  const source = planned?.source ?? {};
  const rows = [["Item", "Value"]];
  asStringArray(planned.formula_lines).forEach((line, index) => {
    rows.push([`formula_${index + 1}`, line]);
  });
  asStringArray(planned.constraints).forEach((line, index) => {
    rows.push([`constraint_${index + 1}`, line]);
  });
  rows.push(["source_path", String(source.path ?? "-")]);
  rows.push(["source_sha256", String(source.sha256 ?? "-")]);

  addTableTracked(slide, rows, {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 5.6,
    fontFace: fontEn,
    fill: "FFFFFF",
    masterSlideName: "appendix_master",
  });
}

function addAppendixA2() {
  const slide = createSlide("appendix_a2_decision_compare", {
    masterName: "appendix_master",
    title: isJa ? "付録 A2 2案比較" : "Appendix A2 Decision Compare",
    message: isJa ? "推奨案と対向案の差分" : "Recommended vs counter differences",
  });

  const compare = spec?.decision_compare ?? {};
  const diff = compare.metric_diff_recommended_minus_counter ?? {};
  const metricRows = [
    ["Metric", "Recommended - Counter"],
    ["min_irr", asNumber(diff.min_irr, 0).toFixed(6)],
    ["min_nbv", asNumber(diff.min_nbv, 0).toLocaleString("en-US", { maximumFractionDigits: 0 })],
    ["min_loading_surplus_ratio", asNumber(diff.min_loading_surplus_ratio, 0).toFixed(6)],
    ["max_premium_to_maturity", asNumber(diff.max_premium_to_maturity, 0).toFixed(6)],
    ["violation_count", `${Math.round(asNumber(diff.violation_count, 0))}`],
  ];
  addTableTracked(slide, metricRows, {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 2.18,
    fontFace: fontEn,
    fill: "FFFFFF",
    autoPage: false,
  });

  const priceRows = [["Model Point", "Rec Annual P", "Ctr Annual P", "Delta"]];
  const diffRows = Array.isArray(compare.price_diff_by_model_point) ? compare.price_diff_by_model_point : [];
  diffRows.forEach((row) => {
    priceRows.push([
      String(row.model_point ?? ""),
      asNumber(row.recommended_annual_premium, 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      asNumber(row.counter_annual_premium, 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      asNumber(row.delta_recommended_minus_counter, 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
    ]);
  });
  addTableTracked(slide, priceRows, {
    x: marginLeft,
    y: bodyTop + 2.3,
    w: contentWidth,
    h: 3.25,
    fontFace: fontEn,
    fill: "FFFFFF",
    autoPage: false,
    masterSlideName: "appendix_master",
  });

  slide.addText(bullets(compare.adoption_reason), {
    x: marginLeft,
    y: bodyTop + 5.6,
    w: contentWidth,
    h: 0.95,
    fontFace: fontJa,
    fontSize: bodyPt * 0.5,
    color: colorSecondary,
    breakLine: true,
  });
  trackEditable();
}

function addAppendixA3() {
  const slide = createSlide("appendix_a3_causal_bridge", {
    masterName: "appendix_master",
    title: isJa ? "付録 A3 橋渡し分解" : "Appendix A3 Causal Bridge",
    message: isJa ? "P差分から利源寄与への分解" : "Premium gap to profit-source contribution",
  });

  const rows = [["Component", "Recommended", "Counter", "Delta", "Contribution Ratio"]];
  const components = Array.isArray(spec?.causal_bridge?.components) ? spec.causal_bridge.components : [];
  components.forEach((row) => {
    rows.push([
      String(row.label ?? row.component ?? ""),
      asNumber(row.recommended_total, 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      asNumber(row.counter_total, 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      asNumber(row.delta_recommended_minus_counter, 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      formatPct(row.contribution_ratio_to_net_delta, 1),
    ]);
  });
  addTableTracked(slide, rows, {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 5.65,
    fontFace: fontEn,
    fill: "FFFFFF",
    masterSlideName: "appendix_master",
  });
}

function addAppendixA4() {
  const slide = createSlide("appendix_a4_sensitivity_decomposition", {
    masterName: "appendix_master",
    title: isJa ? "付録 A4 感応度分解" : "Appendix A4 Sensitivity Decomposition",
    message: isJa ? "支配シナリオ順位" : "Dominant scenario ranking",
  });

  const rows = [["Scenario", "d_min_irr", "d_min_nbv", "d_max_ptm", "d_violations", "risk_score"]];
  const ranked = Array.isArray(spec?.sensitivity_decomposition?.recommended)
    ? spec.sensitivity_decomposition.recommended
    : [];
  ranked.forEach((row) => {
    rows.push([
      String(row.scenario ?? ""),
      asNumber(row.delta_min_irr, 0).toFixed(6),
      asNumber(row.delta_min_nbv, 0).toLocaleString("en-US", { maximumFractionDigits: 0 }),
      asNumber(row.delta_max_ptm, 0).toFixed(6),
      asNumber(row.delta_violation_count, 0).toFixed(0),
      asNumber(row.risk_score, 0).toFixed(4),
    ]);
  });

  addTableTracked(slide, rows, {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 5.65,
    fontFace: fontEn,
    fill: "FFFFFF",
    masterSlideName: "appendix_master",
  });
}

function addAppendixA5() {
  const slide = createSlide("appendix_a5_procon", {
    masterName: "appendix_master",
    title: "Appendix A5 Pro / Con",
    message: isJa ? "定量3 + 定性3" : "Quant 3 + Qual 3",
  });

  const procon = spec?.procon ?? {};
  const rec = procon.recommended ?? {};
  const pros = [
    ...asStringArray((rec?.pros?.quant ?? []).map((row) => row?.text)),
    ...asStringArray((rec?.pros?.qual ?? []).map((row) => row?.text)),
  ];
  const cons = [
    ...asStringArray((rec?.cons?.quant ?? []).map((row) => row?.text)),
    ...asStringArray((rec?.cons?.qual ?? []).map((row) => row?.text)),
  ];

  const colGap = 0.18;
  const colWidth = (contentWidth - colGap) / 2;

  slide.addShape(pptx.ShapeType.roundRect, {
    x: marginLeft,
    y: bodyTop,
    w: colWidth,
    h: 5.65,
    fill: { color: "FFFFFF" },
    line: { color: colorGrid, pt: 1 },
    radius: 0.03,
  });
  trackEditable();

  slide.addShape(pptx.ShapeType.roundRect, {
    x: marginLeft + colWidth + colGap,
    y: bodyTop,
    w: colWidth,
    h: 5.65,
    fill: { color: "FFFFFF" },
    line: { color: colorGrid, pt: 1 },
    radius: 0.03,
  });
  trackEditable();

  slide.addText("Pros", {
    x: marginLeft + 0.12,
    y: bodyTop + 0.1,
    w: colWidth - 0.24,
    h: 0.22,
    fontFace: fontEn,
    fontSize: bodyPt * 0.68,
    color: colorPositive,
    bold: true,
  });
  trackEditable();

  slide.addText("Cons", {
    x: marginLeft + colWidth + colGap + 0.12,
    y: bodyTop + 0.1,
    w: colWidth - 0.24,
    h: 0.22,
    fontFace: fontEn,
    fontSize: bodyPt * 0.68,
    color: colorNegative,
    bold: true,
  });
  trackEditable();

  slide.addText(bullets(pros.slice(0, 6)), {
    x: marginLeft + 0.12,
    y: bodyTop + 0.36,
    w: colWidth - 0.24,
    h: 5.12,
    fontFace: fontJa,
    fontSize: bodyPt * 0.5,
    color: colorText,
    breakLine: true,
    valign: "top",
  });
  trackEditable();

  slide.addText(bullets(cons.slice(0, 6)), {
    x: marginLeft + colWidth + colGap + 0.12,
    y: bodyTop + 0.36,
    w: colWidth - 0.24,
    h: 5.12,
    fontFace: fontJa,
    fontSize: bodyPt * 0.5,
    color: colorText,
    breakLine: true,
    valign: "top",
  });
  trackEditable();
}

function addAppendixA6() {
  const slide = createSlide("appendix_a6_audit_trail", {
    masterName: "appendix_master",
    title: isJa ? "付録 A6 監査証跡" : "Appendix A6 Audit Trail",
    message: "trace_map + formula IDs",
  });

  const rows = [["claim_id", "source_file", "source_path"]];
  const trace = Array.isArray(spec.trace_map) ? spec.trace_map : [];
  trace.forEach((row) => {
    rows.push([
      String(row.claim_id ?? ""),
      String(row.source_file ?? ""),
      String(row.source_path ?? ""),
    ]);
  });

  addTableTracked(slide, rows, {
    x: marginLeft,
    y: bodyTop,
    w: contentWidth,
    h: 5.2,
    fontFace: fontEn,
    fill: "FFFFFF",
    masterSlideName: "appendix_master",
  });

  slide.addText(`formula_id: ${String(spec?.formula_catalog?.planned_expense?.id ?? "-")}`, {
    x: marginLeft,
    y: bodyTop + 5.28,
    w: contentWidth,
    h: 0.26,
    fontFace: fontEn,
    fontSize: bodyPt * 0.5,
    color: colorSecondary,
  });
  trackEditable();
}

addExecutiveSummarySlide();
addDecisionStatementSlide();
addPricingRecommendationSlide();
addConstraintStatusSlide();
addCashflowBridgeSlide();
addProfitSourceDecompositionSlide();
addSensitivitySlide();
addGovernanceSlide();
addDecisionAskSlide();
addAppendixA1();
addAppendixA2();
addAppendixA3();
addAppendixA4();
addAppendixA5();
addAppendixA6();

metrics.slide_count = Array.isArray(pptx?._slides) ? pptx._slides.length : createdSlideCount;

fs.mkdirSync(path.dirname(outPath), { recursive: true });
await pptx.writeFile({ fileName: outPath });

fs.mkdirSync(path.dirname(metricsOutPath), { recursive: true });
fs.writeFileSync(metricsOutPath, JSON.stringify(metrics, null, 2), "utf8");
