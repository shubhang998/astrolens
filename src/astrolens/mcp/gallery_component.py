# ruff: noqa: E501
"""ChatGPT Apps SDK gallery component resources."""

import os
from urllib.parse import urlsplit

GALLERY_URI = "ui://astrolens/gallery.html"

GALLERY_RESOURCE = {
    "uri": GALLERY_URI,
    "name": "AstroLens image gallery",
    "description": "Interactive gallery for AstroLens evidence views and observation previews.",
    "mimeType": "text/html",
}

_BASE_WIDGET_DOMAINS = [
    "https://mast.stsci.edu",
    "https://archive.stsci.edu",
    "https://hla.stsci.edu",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "https://*.trycloudflare.com",
]


def _widget_domains() -> list[str]:
    """Base widget CSP domains plus the deployment origin, when configured."""

    domains = list(_BASE_WIDGET_DOMAINS)
    public_base = os.getenv("ASTROLENS_PUBLIC_BASE_URL", "").strip()
    if public_base:
        parts = urlsplit(public_base)
        if parts.scheme in {"http", "https"} and parts.netloc:
            origin = f"{parts.scheme}://{parts.netloc}"
            if origin not in domains:
                domains.append(origin)
    return domains


_WIDGET_DOMAINS = _widget_domains()

GALLERY_RESOURCE_META = {
    "ui": {
        "prefersBorder": True,
        "csp": {
            "connectDomains": [],
            "resourceDomains": list(_WIDGET_DOMAINS),
        },
    },
    "openai/widgetDescription": (
        "An AstroLens gallery showing public astronomy preview images, source metadata, "
        "citations, and caveats."
    ),
    "openai/widgetPrefersBorder": True,
    "openai/widgetCSP": {
        "connect_domains": [],
        "resource_domains": list(_WIDGET_DOMAINS),
        "redirect_domains": list(_WIDGET_DOMAINS),
    },
}

GALLERY_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AstroLens</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #0a0e17;
      --bg-2: #10161f;
      --panel: #141b26;
      --panel-soft: #1b2430;
      --text: #eef2f8;
      --muted: #9aa7b6;
      --faint: #66727f;
      --line: #262f3c;
      --accent: #6ee7d0;
      --accent-2: #8ab4ff;
      --warn: #f8c46a;
      --radius: 14px;
      --shadow: 0 10px 30px rgba(0,0,0,0.35);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: var(--text);
      background:
        radial-gradient(1100px 500px at 78% -8%, rgba(138,180,255,0.12), transparent 60%),
        radial-gradient(900px 500px at 8% 108%, rgba(110,231,208,0.10), transparent 55%),
        var(--bg);
      -webkit-font-smoothing: antialiased;
    }
    .shell { padding: 18px; max-width: 900px; margin: 0 auto; }
    .hero { margin-bottom: 16px; }
    .eyebrow {
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase;
      color: var(--accent); font-weight: 650; margin-bottom: 8px;
    }
    .eyebrow .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 10px var(--accent); }
    .title { font-size: 26px; line-height: 1.12; font-weight: 750; margin: 0; letter-spacing: -0.01em; }
    .sub { margin: 7px 0 0; color: var(--muted); font-size: 13px; line-height: 1.45; }
    .headline {
      margin: 12px 0 0; font-size: 15px; line-height: 1.5; color: var(--text);
      border-left: 2px solid var(--accent); padding-left: 12px;
    }
    .layout { display: grid; grid-template-columns: 1fr; gap: 16px; }
    @media (min-width: 680px) { .layout { grid-template-columns: 1.15fr 1fr; align-items: start; } }
    .media { display: grid; gap: 12px; min-width: 0; }
    .figure {
      border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden;
      background: var(--panel); box-shadow: var(--shadow);
    }
    .frame { position: relative; background: #04060a; aspect-ratio: 4 / 3; overflow: hidden; }
    .frame img { width: 100%; height: 100%; object-fit: contain; display: block; }
    .chip {
      position: absolute; top: 10px; left: 10px;
      background: rgba(6,10,18,0.72); backdrop-filter: blur(4px);
      border: 1px solid rgba(255,255,255,0.14); color: var(--text);
      border-radius: 999px; padding: 4px 10px; font-size: 11px; font-weight: 600;
    }
    .band-chip { right: 10px; left: auto; color: var(--accent-2); }
    .cap { padding: 11px 13px 13px; }
    .cap-title { font-size: 13px; font-weight: 650; line-height: 1.35; margin: 0 0 5px; }
    .cap-meta { color: var(--muted); font-size: 12px; line-height: 1.4; }
    .cap-links { margin-top: 9px; display: flex; flex-wrap: wrap; gap: 12px; }
    a { color: var(--accent); text-decoration: none; font-size: 12px; font-weight: 600; word-break: break-word; }
    a:hover { text-decoration: underline; }
    .panel {
      border: 1px solid var(--line); border-radius: var(--radius);
      background: linear-gradient(180deg, var(--panel), var(--bg-2));
      padding: 15px; box-shadow: var(--shadow); min-width: 0;
    }
    .panel h2 {
      font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase;
      color: var(--faint); margin: 0 0 12px; font-weight: 700;
    }
    .why { color: var(--muted); font-size: 13px; line-height: 1.55; margin: 0 0 14px; }
    .facts { display: grid; gap: 11px; }
    .fact { display: grid; gap: 3px; padding-bottom: 11px; border-bottom: 1px solid var(--line); }
    .fact:last-child { border-bottom: 0; padding-bottom: 0; }
    .fact-kind {
      font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
      color: var(--accent); font-weight: 700;
    }
    .fact-claim { font-size: 13px; line-height: 1.45; color: var(--text); }
    .fact-scale { font-size: 12.5px; line-height: 1.4; color: var(--accent-2); font-style: italic; }
    .credits { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--line); }
    .credits .lbl { font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--faint); font-weight: 700; }
    .credit-line { color: var(--muted); font-size: 11.5px; line-height: 1.5; margin-top: 4px; }
    .cite { color: var(--faint); font-size: 11px; margin-top: 8px; }
    .empty {
      padding: 20px; border: 1px dashed var(--line); border-radius: var(--radius);
      color: var(--muted); font-size: 13px; text-align: center;
    }
    .caveats {
      margin-top: 16px; border: 1px solid var(--line); border-radius: var(--radius);
      background: rgba(248,196,106,0.06); padding: 12px 14px;
      color: var(--muted); font-size: 12px; line-height: 1.5;
    }
    .caveats .lbl { color: var(--warn); font-weight: 700; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; }
    .caveats ul { margin: 6px 0 0; padding-left: 16px; }
    .caveats li { margin: 3px 0; }
    @media (prefers-color-scheme: light) {
      :root {
        --bg: #fbfcfe; --bg-2: #f2f5fa; --panel: #ffffff; --panel-soft: #eef2f7;
        --text: #10151d; --muted: #4a5666; --faint: #8894a3; --line: #e2e7ef;
        --accent: #0d9488; --accent-2: #3b6fd4; --warn: #b45309;
        --shadow: 0 8px 24px rgba(20,30,50,0.08);
      }
      .frame { background: #0d151f; }
      .chip { background: rgba(255,255,255,0.86); color: var(--text); }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="eyebrow"><span class="dot"></span><span id="eyebrow">AstroLens evidence</span></div>
      <h1 class="title" id="title">AstroLens</h1>
      <p class="sub" id="subtitle"></p>
      <p class="headline" id="headline" hidden></p>
    </section>
    <div class="layout">
      <section class="media" id="media"></section>
      <aside class="panel" id="panel" hidden></aside>
    </div>
    <section class="empty" id="empty" hidden>No image previews were returned for this result.</section>
    <section class="caveats" id="caveats" hidden></section>
  </main>
  <script>
    function getOutput() { return (window.openai && window.openai.toolOutput) || {}; }

    function collectItems(output) {
      if (Array.isArray(output.views) && output.views.length) {
        return output.views.map(viewToItem).filter(Boolean);
      }
      if (Array.isArray(output.observations)) {
        return output.observations.map(observationToItem).filter(Boolean);
      }
      return [];
    }

    function viewToItem(view) {
      const asset = view.asset || {};
      const url = asset.asset_url || asset.thumbnail_url;
      if (!url) return null;
      const products = Array.isArray(view.raw_products) ? view.raw_products : [];
      const bestProduct = products.find((p) => p.preview_url === url || p.download_url === url) || products[0] || {};
      return {
        label: view.label || "AstroLens preview",
        url,
        facility: view.facility || view.source_archive || "",
        instrument: view.instrument || "",
        band: view.band_family || "",
        visualTier: asset.visual_tier || "",
        targetValidation: asset.target_validation || null,
        sourceUrl: bestProduct.download_url || url,
        processed: isProcessedProduct(bestProduct)
      };
    }

    function observationToItem(observation) {
      const asset = observation.asset || {};
      const url = observation.asset_url || asset.asset_url || asset.thumbnail_url;
      if (!url) return null;
      const products = Array.isArray(observation.raw_products) ? observation.raw_products : [];
      const bestProduct = products.find((p) => p.preview_url === url || p.download_url === url) || products[0] || {};
      return {
        label: observation.label || "AstroLens observation",
        url,
        facility: observation.facility || observation.source_archive || "",
        instrument: observation.instrument || "",
        band: observation.band_family || "",
        visualTier: observation.visual_tier || asset.visual_tier || "",
        targetValidation: observation.target_validation || asset.target_validation || null,
        sourceUrl: bestProduct.download_url || url,
        processed: isProcessedProduct(bestProduct)
      };
    }

    function isProcessedProduct(product) {
      const text = [
        product.source_record_id, product.download_url, product.preview_url,
        product.raw_metadata && product.raw_metadata.dataURI,
        product.raw_metadata && product.raw_metadata.productFilename,
        product.raw_metadata && product.raw_metadata.project,
        product.raw_metadata && product.raw_metadata.description
      ].filter(Boolean).join(" ").toLowerCase();
      return text.includes("hla") || text.includes("hlsp") || text.includes("drz") ||
        text.includes("drw") || text.includes("drc") || text.includes("i2d") ||
        text.includes("mosaic") || text.includes("color") || text.includes("hap");
    }

    function render() {
      const output = getOutput();
      const obj = output.object || {};
      const coords = obj.coordinates
        ? "RA " + Number(obj.coordinates.ra_deg).toFixed(4) + ", Dec " + Number(obj.coordinates.dec_deg).toFixed(4)
        : "";
      const items = collectItems(output).slice(0, 2);

      document.getElementById("eyebrow").textContent = obj.type ? String(obj.type) : "AstroLens evidence";
      document.getElementById("title").textContent = obj.name || obj.id || "AstroLens";
      document.getElementById("subtitle").textContent = coords;

      const headlineEl = document.getElementById("headline");
      if (output.headline) { headlineEl.textContent = String(output.headline); headlineEl.hidden = false; }
      else { headlineEl.hidden = true; }

      const media = document.getElementById("media");
      media.innerHTML = "";
      for (const item of items) media.appendChild(renderFigure(item));
      document.getElementById("empty").hidden = items.length > 0 || hasFacts(output);

      renderPanel(output);
      renderCaveats(output, items);
    }

    function renderFigure(item) {
      const fig = document.createElement("figure");
      fig.className = "figure";
      fig.style.margin = "0";
      const quality = tierLabel(item.visualTier, item.processed);
      const band = item.band ? String(item.band) : "";
      const metaBits = [item.facility, item.instrument].filter(Boolean).join(" \\u00b7 ");
      const validation = validationLabel(item.targetValidation);
      fig.innerHTML = `
        <div class="frame">
          <img alt="${escapeHtml(item.label)}" src="${escapeAttribute(safeUrl(item.url))}" loading="lazy" />
          <span class="chip">${escapeHtml(quality)}</span>
          ${band ? `<span class="chip band-chip">${escapeHtml(band)}</span>` : ""}
        </div>
        <figcaption class="cap">
          <p class="cap-title">${escapeHtml(item.label)}</p>
          <div class="cap-meta">${escapeHtml(metaBits)}${validation ? " \\u00b7 " + escapeHtml(validation) : ""}</div>
          <div class="cap-links">
            <a href="${escapeAttribute(safeUrl(item.url))}" target="_blank" rel="noreferrer">Open image</a>
            <a href="${escapeAttribute(safeUrl(item.sourceUrl))}" target="_blank" rel="noreferrer">Source product</a>
          </div>
        </figcaption>`;
      return fig;
    }

    function hasFacts(output) {
      return Array.isArray(output.object_facts) && output.object_facts.length > 0;
    }

    function renderPanel(output) {
      const panel = document.getElementById("panel");
      const facts = Array.isArray(output.object_facts) ? output.object_facts : [];
      const why = output.why_interesting ? String(output.why_interesting) : "";
      const credits = Array.isArray(output.credits) ? output.credits : [];
      const factCites = Array.isArray(output.fact_citations) ? output.fact_citations : [];
      if (!facts.length && !why && !credits.length) { panel.hidden = true; return; }
      panel.hidden = false;

      let html = "<h2>The numbers</h2>";
      if (why) html += `<p class="why">${escapeHtml(why)}</p>`;
      if (facts.length) {
        html += '<div class="facts">';
        for (const fact of facts.slice(0, 12)) {
          const kind = fact.quantity_kind ? String(fact.quantity_kind).replace(/_/g, " ") : "";
          html += '<div class="fact">';
          if (kind) html += `<div class="fact-kind">${escapeHtml(kind)}</div>`;
          html += `<div class="fact-claim">${escapeHtml(fact.claim || "")}</div>`;
          if (fact.scale_comparison) html += `<div class="fact-scale">${escapeHtml(fact.scale_comparison)}</div>`;
          html += "</div>";
        }
        html += "</div>";
      }
      if (credits.length) {
        html += '<div class="credits"><div class="lbl">Credit</div>';
        const seen = {};
        for (const c of credits) {
          const line = (c && c.credit_line) ? String(c.credit_line) : "";
          if (!line || seen[line]) continue;
          seen[line] = true;
          html += `<div class="credit-line">${escapeHtml(line)}</div>`;
        }
        html += "</div>";
      }
      if (factCites.length) {
        const names = [];
        for (const c of factCites) { if (c && c.title && names.indexOf(c.title) < 0) names.push(String(c.title)); }
        if (names.length) html += `<div class="cite">Facts from ${escapeHtml(names.slice(0, 3).join(", "))}.</div>`;
      }
      panel.innerHTML = html;
    }

    function renderCaveats(output, items) {
      const warnings = Array.isArray(output.warnings)
        ? output.warnings.map((w) => (w && w.message) ? w.message : String(w)) : [];
      const viewCaveats = [];
      const rawViews = Array.isArray(output.views) ? output.views : [];
      for (const v of rawViews) { if (Array.isArray(v.caveats)) viewCaveats.push.apply(viewCaveats, v.caveats); }
      const all = [];
      for (const c of warnings.concat(viewCaveats)) { if (c && all.indexOf(c) < 0) all.push(c); }
      const node = document.getElementById("caveats");
      if (!all.length) { node.hidden = true; return; }
      node.hidden = false;
      node.innerHTML = '<div class="lbl">Caveats</div><ul>' +
        all.slice(0, 5).map((c) => "<li>" + escapeHtml(c) + "</li>").join("") + "</ul>";
    }

    function tierLabel(tier, processed) {
      const labels = {
        outreach_release: "outreach image",
        astrolens_rendered: "AstroLens render",
        processed_archive: "processed archive",
        raw_archive_preview: "raw preview",
        unknown: processed ? "processed preview" : "archive preview"
      };
      return labels[tier] || (processed ? "processed preview" : "archive preview");
    }

    function validationLabel(validation) {
      if (!validation || !validation.status) return "";
      const confidence = typeof validation.confidence === "number"
        ? " " + Math.round(validation.confidence * 100) + "%" : "";
      return String(validation.status).replace(/_/g, " ") + confidence;
    }

    function escapeHtml(value) {
      return String(value == null ? "" : value)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }
    function escapeAttribute(value) { return escapeHtml(value).replace(/`/g, "&#096;"); }
    function safeUrl(value) {
      const url = String(value || "");
      if (url.startsWith("https://") || url.startsWith("http://") || url.startsWith("/")) return url;
      return "about:blank";
    }

    window.addEventListener("openai:set_globals", render);
    document.addEventListener("DOMContentLoaded", render);
    render();
  </script>
</body>
</html>
""".strip()
