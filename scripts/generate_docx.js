#!/usr/bin/env node
/**
 * ARIS — DOCX Generator
 * Reads JSON from stdin, writes .docx to stdout (base64) or a file path.
 *
 * Input JSON shape:
 * {
 *   "type":    "gap_analysis" | "synthesis" | "brief",
 *   "outpath": "/path/to/output.docx",
 *   "data":    { ...type-specific fields }
 * }
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageNumber, Footer, Header,
} = require('docx');
const fs = require('fs');

const input = JSON.parse(fs.readFileSync('/dev/stdin', 'utf8'));
const { type, outpath, data } = input;

// ── Helpers ───────────────────────────────────────────────────────────────────

const BRAND_BLUE  = '1A5EAB';
const GRAY_LIGHT  = 'F2F2F2';
const GRAY_MED    = 'CCCCCC';
const RED         = 'C0392B';
const ORANGE      = 'E67E22';
const YELLOW      = 'F39C12';
const GREEN       = '27AE60';

function border(color = GRAY_MED) {
  const b = { style: BorderStyle.SINGLE, size: 1, color };
  return { top: b, bottom: b, left: b, right: b };
}

function cell(text, opts = {}) {
  const { bold = false, shade = null, width = null, color = '000000' } = opts;
  const cellOpts = {
    borders: border(),
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({
      children: [new TextRun({ text: String(text || ''), bold, font: 'Arial', size: 20, color })],
    })],
  };
  if (shade) cellOpts.shading = { fill: shade, type: ShadingType.CLEAR };
  if (width) cellOpts.width = { size: width, type: WidthType.DXA };
  return new TableCell(cellOpts);
}

function heading1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text, font: 'Arial', size: 32, bold: true, color: BRAND_BLUE })],
    spacing: { before: 240, after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BRAND_BLUE, space: 1 } },
  });
}

function heading2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, font: 'Arial', size: 26, bold: true, color: '2C3E50' })],
    spacing: { before: 200, after: 80 },
  });
}

function body(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text: String(text || ''), font: 'Arial', size: 22,
      bold: opts.bold, color: opts.color || '333333' })],
    spacing: { before: 60, after: 60 },
  });
}

function bulletPara(text) {
  return new Paragraph({
    numbering: { reference: 'bullets', level: 0 },
    children: [new TextRun({ text: String(text || ''), font: 'Arial', size: 20, color: '333333' })],
    spacing: { before: 40, after: 40 },
  });
}

function spacer() {
  return new Paragraph({ children: [new TextRun('')], spacing: { before: 60, after: 60 } });
}

function metaRow(label, value) {
  return new Paragraph({
    children: [
      new TextRun({ text: label + ': ', font: 'Arial', size: 20, bold: true, color: '555555' }),
      new TextRun({ text: String(value || '—'), font: 'Arial', size: 20, color: '333333' }),
    ],
    spacing: { before: 40, after: 40 },
  });
}

function severityColor(sev) {
  const s = (sev || '').toLowerCase();
  if (s === 'critical') return RED;
  if (s === 'high')     return ORANGE;
  if (s === 'medium')   return YELLOW;
  return GREEN;
}

const NUMBERING = {
  config: [{
    reference: 'bullets',
    levels: [{ level: 0, format: LevelFormat.BULLET, text: '\u2022', alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } } }],
  }],
};

// ── Gap Analysis export ───────────────────────────────────────────────────────

function buildGapAnalysis(d) {
  const gaps   = (d.gaps_result?.gaps           || []);
  const comply = (d.gaps_result?.compliant_areas || []);
  const road   = (d.gaps_result?.priority_roadmap || []);
  const score  = d.posture_score ?? 0;
  const date   = (d.generated_at || new Date().toISOString()).slice(0, 10);

  const children = [
    // Title
    new Paragraph({
      children: [new TextRun({ text: 'Compliance Gap Analysis', font: 'Arial', size: 48, bold: true, color: BRAND_BLUE })],
      spacing: { after: 80 },
    }),
    new Paragraph({
      children: [new TextRun({ text: 'Automated Regulatory Intelligence System (ARIS)', font: 'Arial', size: 22, color: '888888' })],
      spacing: { after: 200 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BRAND_BLUE, space: 1 } },
    }),
    spacer(),

    // Metadata
    metaRow('Company', d.profile_name),
    metaRow('Jurisdictions', (d.jurisdictions || []).join(', ')),
    metaRow('Documents examined', d.docs_examined),
    metaRow('Generated', date),
    metaRow('Model', d.model_used || 'Claude'),
    spacer(),

    // Posture score
    heading1('Compliance Posture'),
    new Paragraph({
      children: [
        new TextRun({ text: `Score: `, font: 'Arial', size: 24, bold: true }),
        new TextRun({ text: `${score}/100`, font: 'Arial', size: 28, bold: true,
          color: score >= 70 ? GREEN : score >= 40 ? YELLOW : RED }),
      ],
      spacing: { before: 80, after: 80 },
    }),
  ];

  if (d.gaps_result?.posture_summary) {
    children.push(body(d.gaps_result.posture_summary));
  }

  // Summary stats
  children.push(spacer());
  const statsTable = new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2340, 2340, 2340, 2340],
    rows: [
      new TableRow({ children: [
        cell('Critical Gaps', { bold: true, shade: 'FDECEA', width: 2340 }),
        cell('Total Gaps',    { bold: true, shade: GRAY_LIGHT, width: 2340 }),
        cell('Compliant Areas', { bold: true, shade: 'EAF4EA', width: 2340 }),
        cell('Regs Reviewed', { bold: true, shade: GRAY_LIGHT, width: 2340 }),
      ]}),
      new TableRow({ children: [
        cell(d.critical_count ?? 0, { color: RED,   width: 2340 }),
        cell(d.gap_count     ?? 0,  { color: ORANGE, width: 2340 }),
        cell(comply.length,          { color: GREEN, width: 2340 }),
        cell(d.applicable_count ?? 0, { width: 2340 }),
      ]}),
    ],
  });
  children.push(statsTable, spacer());

  // Gaps
  if (gaps.length > 0) {
    children.push(heading1(`Compliance Gaps (${gaps.length})`));
    const sorted = [...gaps].sort((a, b) =>
      (['Critical','High','Medium','Low'].indexOf(a.severity) || 4) -
      (['Critical','High','Medium','Low'].indexOf(b.severity) || 4)
    );
    for (const gap of sorted) {
      const col = severityColor(gap.severity);
      children.push(
        new Paragraph({
          children: [
            new TextRun({ text: `[${(gap.severity||'').toUpperCase()}]  `, font: 'Arial', size: 22, bold: true, color: col }),
            new TextRun({ text: gap.title || '', font: 'Arial', size: 22, bold: true, color: '2C3E50' }),
          ],
          spacing: { before: 180, after: 40 },
        }),
        metaRow('Regulation', gap.regulation_title),
        metaRow('Jurisdiction', gap.jurisdiction),
        metaRow('Effort', gap.effort_estimate),
      );
      if (gap.obligation) children.push(body('Obligation: ' + gap.obligation, { bold: false }));
      if (gap.gap_description) children.push(body('Gap: ' + gap.gap_description));
      if (gap.first_action) {
        children.push(new Paragraph({
          children: [
            new TextRun({ text: 'First Action: ', font: 'Arial', size: 20, bold: true, color: BRAND_BLUE }),
            new TextRun({ text: gap.first_action, font: 'Arial', size: 20, color: '333333' }),
          ],
          spacing: { before: 60, after: 120 },
        }));
      }
    }
    children.push(spacer());
  }

  // Compliant areas
  if (comply.length > 0) {
    children.push(heading1(`Compliant Areas (${comply.length})`));
    for (const c of comply) {
      children.push(
        new Paragraph({
          children: [new TextRun({ text: c.area || '', font: 'Arial', size: 22, bold: true, color: GREEN })],
          spacing: { before: 100, after: 30 },
        }),
        body(c.evidence || ''),
      );
    }
    children.push(spacer());
  }

  // Roadmap
  if (road.length > 0) {
    children.push(heading1('Remediation Roadmap'));
    for (const phase of road) {
      children.push(heading2(phase.phase || 'Phase'));
      for (const action of (phase.actions || [])) {
        children.push(bulletPara(action));
      }
    }
    children.push(spacer());
  }

  // Footer note
  children.push(new Paragraph({
    children: [new TextRun({ text: `Generated by ARIS on ${date}. This report is based on AI analysis and should be reviewed by qualified legal counsel.`,
      font: 'Arial', size: 18, color: '888888', italics: true })],
    spacing: { before: 240 },
    border: { top: { style: BorderStyle.SINGLE, size: 4, color: GRAY_MED, space: 1 } },
  }));

  return new Document({ numbering: NUMBERING, styles: docStyles(), sections: [{ children }] });
}

// ── Synthesis export ──────────────────────────────────────────────────────────

function buildSynthesis(d) {
  const syn      = d.synthesis_json || {};
  const conflicts= d.conflicts_json || {};
  const date     = (d.generated_at || new Date().toISOString()).slice(0, 10);

  const children = [
    new Paragraph({
      children: [new TextRun({ text: 'Regulatory Synthesis', font: 'Arial', size: 48, bold: true, color: BRAND_BLUE })],
      spacing: { after: 80 },
    }),
    new Paragraph({
      children: [new TextRun({ text: d.topic || '', font: 'Arial', size: 28, color: '2C3E50' })],
      spacing: { after: 200 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BRAND_BLUE, space: 1 } },
    }),
    spacer(),
    metaRow('Jurisdictions', (d.jurisdictions || []).join(', ')),
    metaRow('Documents used', d.docs_used),
    metaRow('Generated', date),
    metaRow('Model', d.model_used || 'Claude'),
    spacer(),
  ];

  if (syn.executive_summary || syn.summary) {
    children.push(heading1('Executive Summary'), body(syn.executive_summary || syn.summary || ''), spacer());
  }

  if (syn.themes?.length) {
    children.push(heading1('Key Themes'));
    for (const t of syn.themes) {
      children.push(heading2(t.title || t.theme || ''), body(t.description || t.analysis || ''));
      if (t.jurisdictions?.length) children.push(metaRow('Jurisdictions', t.jurisdictions.join(', ')));
    }
    children.push(spacer());
  }

  if (syn.regulatory_gaps?.length || syn.gaps?.length) {
    const gapList = syn.regulatory_gaps || syn.gaps || [];
    children.push(heading1('Regulatory Gaps & Tensions'));
    for (const g of gapList) children.push(bulletPara(typeof g === 'string' ? g : g.description || JSON.stringify(g)));
    children.push(spacer());
  }

  const conflictList = conflicts.conflicts || conflicts.list || [];
  if (conflictList.length) {
    children.push(heading1('Conflicts Detected'));
    for (const c of conflictList) {
      children.push(
        heading2(c.type || c.title || 'Conflict'),
        body(c.description || c.summary || ''),
        c.jurisdictions?.length ? metaRow('Jurisdictions', c.jurisdictions.join(' vs ')) : null,
      ).filter(Boolean);
    }
    children.push(spacer());
  }

  if (syn.recommendations?.length) {
    children.push(heading1('Recommendations'));
    for (const r of syn.recommendations) children.push(bulletPara(typeof r === 'string' ? r : r.recommendation || JSON.stringify(r)));
    children.push(spacer());
  }

  children.push(new Paragraph({
    children: [new TextRun({ text: `Generated by ARIS on ${date}. AI-assisted analysis — review with qualified counsel.`,
      font: 'Arial', size: 18, color: '888888', italics: true })],
    spacing: { before: 240 },
    border: { top: { style: BorderStyle.SINGLE, size: 4, color: GRAY_MED, space: 1 } },
  }));

  return new Document({ numbering: NUMBERING, styles: docStyles(), sections: [{ children: children.filter(Boolean) }] });
}

// ── Styles ────────────────────────────────────────────────────────────────────

function docStyles() {
  return {
    default: { document: { run: { font: 'Arial', size: 22 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 32, bold: true, font: 'Arial', color: BRAND_BLUE },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 26, bold: true, font: 'Arial', color: '2C3E50' },
        paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 1 } },
    ],
  };
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  let doc;
  if (type === 'gap_analysis') {
    doc = buildGapAnalysis(data);
  } else if (type === 'synthesis') {
    doc = buildSynthesis(data);
  } else {
    process.stderr.write(`Unknown type: ${type}\n`);
    process.exit(1);
  }

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outpath, buffer);
  process.stdout.write(JSON.stringify({ ok: true, bytes: buffer.length }));
}

main().catch(e => {
  process.stderr.write(e.toString() + '\n');
  process.exit(1);
});
