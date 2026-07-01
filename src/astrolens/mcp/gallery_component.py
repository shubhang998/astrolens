# ruff: noqa: E501
"""ChatGPT Apps SDK gallery component resources."""

GALLERY_URI = "ui://astrolens/gallery.html"

GALLERY_RESOURCE = {
    "uri": GALLERY_URI,
    "name": "AstroLens image gallery",
    "description": "Interactive gallery for AstroLens evidence views and observation previews.",
    "mimeType": "text/html",
}

GALLERY_RESOURCE_META = {
    "ui": {
        "prefersBorder": True,
        "csp": {
            "connectDomains": [],
            "resourceDomains": [
                "https://mast.stsci.edu",
                "https://archive.stsci.edu",
                "https://hla.stsci.edu",
                "http://127.0.0.1:8000",
                "http://localhost:8000",
                "https://*.trycloudflare.com",
            ],
        },
    },
    "openai/widgetDescription": (
        "An AstroLens gallery showing public astronomy preview images, source metadata, "
        "citations, and caveats."
    ),
    "openai/widgetPrefersBorder": True,
    "openai/widgetCSP": {
        "connect_domains": [],
        "resource_domains": [
            "https://mast.stsci.edu",
            "https://archive.stsci.edu",
            "https://hla.stsci.edu",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "https://*.trycloudflare.com",
        ],
        "redirect_domains": [
            "https://mast.stsci.edu",
            "https://archive.stsci.edu",
            "https://hla.stsci.edu",
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "https://*.trycloudflare.com",
        ],
    },
}

GALLERY_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AstroLens Gallery</title>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #0d1117;
      --panel: #151b23;
      --panel-soft: #1f2630;
      --text: #edf2f7;
      --muted: #9ba7b4;
      --line: #2e3743;
      --accent: #5eead4;
      --warn: #fbbf24;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    .shell { padding: 14px; }
    .header {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line);
    }
    .title {
      font-size: 16px;
      line-height: 1.25;
      font-weight: 700;
      margin: 0;
    }
    .sub {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      height: 24px;
      border: 1px solid var(--line);
      background: var(--panel-soft);
      border-radius: 999px;
      padding: 0 9px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      padding-top: 14px;
    }
    .card {
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: var(--panel);
      min-width: 0;
    }
    .imageWrap {
      position: relative;
      background: #05070a;
      aspect-ratio: 1.25 / 1;
      overflow: hidden;
    }
    .imageWrap img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }
    .quality {
      position: absolute;
      top: 8px;
      left: 8px;
      background: rgba(3, 7, 18, 0.76);
      border: 1px solid rgba(255,255,255,0.16);
      color: var(--text);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 11px;
    }
    .body { padding: 10px; }
    .label {
      font-size: 13px;
      line-height: 1.35;
      font-weight: 650;
      margin: 0 0 8px;
    }
    .meta {
      display: grid;
      gap: 4px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
      margin-bottom: 9px;
    }
    .links {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    a {
      color: var(--accent);
      text-decoration: none;
      font-size: 12px;
      word-break: break-word;
    }
    a:hover { text-decoration: underline; }
    .empty {
      padding: 18px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      color: var(--muted);
      font-size: 13px;
      margin-top: 14px;
    }
    .caveats {
      margin-top: 14px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .caveats strong { color: var(--warn); font-weight: 650; }
    @media (prefers-color-scheme: light) {
      :root {
        --bg: #ffffff;
        --panel: #f8fafc;
        --panel-soft: #eef2f7;
        --text: #111827;
        --muted: #526070;
        --line: #d8dee8;
        --accent: #047857;
        --warn: #b45309;
      }
      .quality { background: rgba(255,255,255,0.86); color: var(--text); }
      .imageWrap { background: #111827; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="header">
      <div>
        <h1 class="title" id="title">AstroLens</h1>
        <p class="sub" id="subtitle"></p>
      </div>
      <div class="badge" id="count"></div>
    </section>
    <section class="grid" id="grid"></section>
    <section class="empty" id="empty" hidden>No image previews were returned for this result.</section>
    <section class="caveats" id="caveats" hidden></section>
  </main>
  <script>
    function getOutput() {
      return (window.openai && window.openai.toolOutput) || {};
    }

    function collectItems(output) {
      if (Array.isArray(output.views)) {
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
        selectionReason: asset.selection_reason || "",
        targetValidation: asset.target_validation || null,
        provenance: asset.provenance || null,
        productType: bestProduct.product_type || "",
        calibration: bestProduct.calibration_level || "",
        sourceRecord: bestProduct.source_record_id || "",
        sourceUrl: bestProduct.download_url || url,
        caveats: view.caveats || [],
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
        selectionReason: asset.selection_reason || "",
        targetValidation: observation.target_validation || asset.target_validation || null,
        provenance: observation.provenance || asset.provenance || null,
        productType: bestProduct.product_type || "",
        calibration: bestProduct.calibration_level || "",
        sourceRecord: bestProduct.source_record_id || "",
        sourceUrl: bestProduct.download_url || url,
        caveats: observation.caveats || [],
        processed: isProcessedProduct(bestProduct)
      };
    }

    function isProcessedProduct(product) {
      const text = [
        product.source_record_id,
        product.download_url,
        product.preview_url,
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
      const title = obj.name || obj.id || "AstroLens";
      const coords = obj.coordinates
        ? "RA " + Number(obj.coordinates.ra_deg).toFixed(5) + ", Dec " + Number(obj.coordinates.dec_deg).toFixed(5)
        : "";
      const items = collectItems(output);

      document.getElementById("title").textContent = title;
      document.getElementById("subtitle").textContent = [obj.type, coords].filter(Boolean).join(" | ");
      document.getElementById("count").textContent = items.length + " image" + (items.length === 1 ? "" : "s");

      const grid = document.getElementById("grid");
      grid.innerHTML = "";
      for (const item of items) {
        grid.appendChild(renderCard(item));
      }
      document.getElementById("empty").hidden = items.length > 0;

      const caveats = collectCaveats(output, items);
      const caveatNode = document.getElementById("caveats");
      caveatNode.hidden = caveats.length === 0;
      caveatNode.innerHTML = caveats.length
        ? "<strong>Caveats</strong><br>" + caveats.map(escapeHtml).join("<br>")
        : "";
    }

    function renderCard(item) {
      const card = document.createElement("article");
      card.className = "card";
      const quality = tierLabel(item.visualTier, item.processed);
      const validation = validationLabel(item.targetValidation);
      card.innerHTML = `
        <div class="imageWrap">
          <img alt="${escapeHtml(item.label)}" src="${escapeAttribute(item.url)}" loading="lazy" />
          <div class="quality">${escapeHtml(quality)}</div>
        </div>
        <div class="body">
          <p class="label">${escapeHtml(item.label)}</p>
          <div class="meta">
            <div>${escapeHtml(item.facility)}</div>
            <div>${escapeHtml([item.instrument, item.band].filter(Boolean).join(" | "))}</div>
            <div>${escapeHtml([item.productType, item.calibration ? "cal " + item.calibration : ""].filter(Boolean).join(" | "))}</div>
            <div>${escapeHtml(validation)}</div>
          </div>
          <div class="links">
            <a href="${escapeAttribute(item.url)}" target="_blank" rel="noreferrer">Preview</a>
            <a href="${escapeAttribute(item.sourceUrl)}" target="_blank" rel="noreferrer">Source product</a>
          </div>
        </div>`;
      return card;
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
      if (!validation || !validation.status) return "target unverified";
      const confidence = typeof validation.confidence === "number"
        ? " " + Math.round(validation.confidence * 100) + "%"
        : "";
      return validation.status.replace(/_/g, " ") + confidence;
    }

    function collectCaveats(output, items) {
      const warnings = Array.isArray(output.warnings) ? output.warnings.map((w) => w.message || String(w)) : [];
      const viewCaveats = items.flatMap((item) => item.caveats || []);
      return Array.from(new Set([...warnings, ...viewCaveats])).slice(0, 5);
    }

    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    function escapeAttribute(value) {
      return escapeHtml(value).replace(/`/g, "&#096;");
    }

    window.addEventListener("openai:set_globals", render);
    document.addEventListener("DOMContentLoaded", render);
    render();
  </script>
</body>
</html>
""".strip()
