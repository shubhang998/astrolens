# ruff: noqa: E501
"""ChatGPT Apps SDK gallery component resources."""

import hashlib
import os
from urllib.parse import urlsplit

# The URI embeds a hash of the widget HTML: ChatGPT caches widget templates
# by URI, so content changes must change the URI to actually reach users.
GALLERY_URI_PREFIX = "ui://astrolens/gallery"


def _gallery_uri(html: str) -> str:
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()[:10]
    return f"{GALLERY_URI_PREFIX}-{digest}.html"

GALLERY_RESOURCE = {
    "uri": GALLERY_URI_PREFIX + ".html",  # finalized after GALLERY_HTML below
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
      --bg: #0b0f16; --card: #11161f; --card-2: #161d28;
      --text: #eef2f8; --muted: #9aa7b6; --faint: #6b7684; --line: #232c38;
      --accent: #6ee7d0; --link: #7cc4ff; --warn: #f8c46a;
      --radius: 16px; --shadow: 0 12px 32px rgba(0,0,0,0.38);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; padding: 14px;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg); color: var(--text); -webkit-font-smoothing: antialiased;
    }
    .card {
      max-width: 620px; margin: 0 auto; background: var(--card);
      border: 1px solid var(--line); border-radius: var(--radius);
      overflow: hidden; box-shadow: var(--shadow);
    }
    .mosaic { display: grid; gap: 2px; background: var(--line); }
    .mosaic.two { grid-template-columns: 1.9fr 1fr; }
    .mosaic.three { grid-template-columns: 2fr 1fr; grid-template-rows: 150px 150px; }
    .tile { position: relative; background: #04060a; overflow: hidden; }
    .mosaic.one .tile { aspect-ratio: 16 / 9; }
    .mosaic.two .tile { aspect-ratio: auto; height: 300px; }
    .mosaic.three .tile { aspect-ratio: auto; height: auto; }
    .mosaic.three .tile:first-child { grid-row: span 2; }
    .tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .tile a { display: block; width: 100%; height: 100%; }
    .chip {
      position: absolute; z-index: 2; top: 10px; left: 10px;
      background: rgba(5,9,16,0.72); backdrop-filter: blur(4px);
      border: 1px solid rgba(255,255,255,0.16); color: #fff;
      border-radius: 999px; padding: 3px 9px; font-size: 10.5px; font-weight: 650;
    }
    .chip.right { left: auto; right: 10px; color: var(--accent); }
    .body { padding: 18px 20px 16px; }
    h1.title { margin: 0; font-size: 24px; line-height: 1.15; font-weight: 750; letter-spacing: -0.01em; }
    .subtitle { margin: 3px 0 0; color: var(--muted); font-size: 13px; }
    .desc { margin: 12px 0 0; font-size: 13.5px; line-height: 1.55; color: var(--text); }
    .desc .more { color: var(--muted); }
    .ai-badge {
      display: inline-block; margin-right: 6px; vertical-align: 1px;
      border: 1px solid var(--line); background: var(--card-2); color: var(--muted);
      border-radius: 999px; padding: 1px 8px; font-size: 10px; font-weight: 700;
      letter-spacing: 0.04em; text-transform: uppercase; white-space: nowrap;
    }
    .facts { margin: 14px 0 0; border-top: 1px solid var(--line); padding-top: 12px; display: grid; gap: 7px; }
    .factrow { font-size: 13px; line-height: 1.5; }
    .factrow b { font-weight: 700; color: var(--text); }
    .factrow .val { color: var(--muted); }
    .factrow .scale { color: var(--faint); font-style: italic; }
    .imglinks { margin: 12px 0 0; font-size: 11.5px; color: var(--faint); line-height: 1.6; }
    a { color: var(--link); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .chips-title {
      margin: 16px 0 8px; font-size: 11px; letter-spacing: 0.1em;
      text-transform: uppercase; color: var(--faint); font-weight: 700;
      border-top: 1px solid var(--line); padding-top: 14px;
    }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; }
    .qchip {
      border: 1px solid var(--line); background: var(--card-2); color: var(--text);
      border-radius: 999px; padding: 7px 13px; font-size: 12.5px; font-weight: 550;
      cursor: pointer; transition: border-color 0.15s;
      font-family: inherit;
    }
    .qchip:hover { border-color: var(--accent); }
    .footer { padding: 12px 20px 16px; border-top: 1px solid var(--line); background: var(--card-2); }
    .credit { color: var(--faint); font-size: 11px; line-height: 1.55; }
    .caveats { margin-top: 8px; color: var(--faint); font-size: 11px; line-height: 1.55; }
    .caveats b { color: var(--warn); font-weight: 700; }
    .empty { padding: 22px; text-align: center; color: var(--muted); font-size: 13px; }
    @media (max-width: 480px) {
      .mosaic.two { grid-template-columns: 1fr; }
      .mosaic.two .tile { height: 220px; }
      .mosaic.three { grid-template-columns: 1fr 1fr; grid-template-rows: 180px 110px; }
      .mosaic.three .tile:first-child { grid-row: auto; grid-column: span 2; }
    }
    @media (prefers-color-scheme: light) {
      :root {
        --bg: #f2f4f8; --card: #ffffff; --card-2: #f7f9fc;
        --text: #131722; --muted: #4d5866; --faint: #85909e; --line: #e3e8ef;
        --accent: #0d9488; --link: #1a6fd4; --warn: #b45309;
        --shadow: 0 8px 26px rgba(24,34,54,0.10);
      }
      .chip { background: rgba(255,255,255,0.88); color: var(--text); border-color: rgba(0,0,0,0.1); }
      .chip.right { color: var(--accent); }
    }
  </style>
</head>
<body>
  <article class="card">
    <section class="mosaic" id="mosaic" hidden></section>
    <section class="body">
      <h1 class="title" id="title">AstroLens</h1>
      <p class="subtitle" id="subtitle"></p>
      <p class="desc" id="desc" hidden></p>
      <div class="facts" id="facts" hidden></div>
      <div class="imglinks" id="imglinks" hidden></div>
      <div id="chipsWrap" hidden>
        <div class="chips-title">Keep exploring</div>
        <div class="chips" id="chips"></div>
      </div>
    </section>
    <section class="footer" id="footer" hidden>
      <div class="credit" id="credit"></div>
      <div class="caveats" id="caveats" hidden></div>
    </section>
    <section class="empty" id="empty" hidden>No image previews were returned for this result.</section>
  </article>
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
        band: view.band_family || "",
        visualTier: asset.visual_tier || "",
        sourceUrl: bestProduct.download_url || url
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
        band: observation.band_family || "",
        visualTier: observation.visual_tier || asset.visual_tier || "",
        sourceUrl: bestProduct.download_url || url
      };
    }

    function tierLabel(tier) {
      const labels = {
        outreach_release: "outreach image",
        astrolens_rendered: "AstroLens render",
        processed_archive: "processed archive",
        raw_archive_preview: "raw preview"
      };
      return labels[tier] || "archive preview";
    }

    function render() {
      const output = getOutput();
      const obj = output.object || {};
      const coords = obj.coordinates
        ? "RA " + Number(obj.coordinates.ra_deg).toFixed(3) + " \u00b7 Dec " + Number(obj.coordinates.dec_deg).toFixed(3)
        : "";
      const items = collectItems(output).slice(0, 3);

      renderMosaic(items);
      document.getElementById("title").textContent = obj.name || obj.id || "AstroLens";
      document.getElementById("subtitle").textContent = [obj.type, coords].filter(Boolean).join(" \u00b7 ");
      renderDescription(output);
      renderPanel(output);
      renderImageLinks(items);
      renderChips(output);
      renderFooter(output);
      document.getElementById("empty").hidden = items.length > 0 || hasFacts(output);
    }

    function renderMosaic(items) {
      const mosaic = document.getElementById("mosaic");
      mosaic.innerHTML = "";
      if (!items.length) { mosaic.hidden = true; return; }
      mosaic.hidden = false;
      mosaic.className = "mosaic " + (items.length === 1 ? "one" : items.length === 2 ? "two" : "three");
      for (const item of items) {
        const tile = document.createElement("div");
        tile.className = "tile";
        tile.innerHTML = `
          <span class="chip">${escapeHtml(tierLabel(item.visualTier))}</span>
          ${item.band ? `<span class="chip right">${escapeHtml(String(item.band))}</span>` : ""}
          <a href="${escapeAttribute(safeUrl(item.url))}" target="_blank" rel="noreferrer">
            <img alt="${escapeHtml(item.label)}" src="${escapeAttribute(safeUrl(item.url))}" loading="lazy" />
          </a>`;
        mosaic.appendChild(tile);
      }
    }

    function renderDescription(output) {
      const desc = document.getElementById("desc");
      const summary = (output.summary && output.summary.text) ? String(output.summary.text) : "";
      if (summary) {
        // Labeled interpretation: the facts rows below stay the canonical data.
        desc.hidden = false;
        desc.innerHTML = `<span class="ai-badge">AI summary · Sonnet</span> ${escapeHtml(summary)}`;
        return;
      }
      const headline = output.headline ? String(output.headline) : "";
      const why = output.why_interesting ? String(output.why_interesting) : "";
      if (!headline && !why) { desc.hidden = true; return; }
      desc.hidden = false;
      desc.innerHTML = escapeHtml(headline) + (why ? ` <span class="more">${escapeHtml(why)}</span>` : "");
    }

    function hasFacts(output) {
      return Array.isArray(output.object_facts) && output.object_facts.length > 0;
    }

    function factLabel(kind) {
      const raw = String(kind || "").replace(/_/g, " ");
      return raw.charAt(0).toUpperCase() + raw.slice(1);
    }

    function factValue(fact) {
      if (typeof fact.value === "number" && fact.unit && fact.unit !== "dimensionless") {
        return Number(fact.value).toLocaleString(undefined, { maximumFractionDigits: 2 }) + " " + fact.unit;
      }
      if (typeof fact.value === "number") {
        return Number(fact.value).toLocaleString(undefined, { maximumFractionDigits: 5 });
      }
      return fact.claim || "";
    }

    function renderPanel(output) {
      const facts = Array.isArray(output.object_facts) ? output.object_facts : [];
      const node = document.getElementById("facts");
      if (!facts.length) { node.hidden = true; return; }
      node.hidden = false;
      node.innerHTML = "";
      const headline = output.headline ? String(output.headline) : "";
      for (const fact of facts.slice(0, 10)) {
        if (fact.claim && fact.claim === headline) continue;  // shown above already
        const row = document.createElement("div");
        row.className = "factrow";
        const label = fact.quantity_kind ? factLabel(fact.quantity_kind) : "";
        const scale = fact.scale_comparison ? ` <span class="scale">(${escapeHtml(fact.scale_comparison)})</span>` : "";
        if (label && (typeof fact.value === "number")) {
          row.innerHTML = `<b>${escapeHtml(label)}:</b> <span class="val">${escapeHtml(factValue(fact))}</span>${scale}`;
        } else {
          row.innerHTML = `${label ? `<b>${escapeHtml(label)}:</b> ` : ""}<span class="val">${escapeHtml(fact.claim || "")}</span>${scale}`;
        }
        node.appendChild(row);
      }
    }

    function renderImageLinks(items) {
      const node = document.getElementById("imglinks");
      if (!items.length) { node.hidden = true; return; }
      node.hidden = false;
      node.innerHTML = items.map((item, index) =>
        `${index + 1}. ${escapeHtml(item.label)} \u2014 ` +
        `<a href="${escapeAttribute(safeUrl(item.url))}" target="_blank" rel="noreferrer">open</a> \u00b7 ` +
        `<a href="${escapeAttribute(safeUrl(item.sourceUrl))}" target="_blank" rel="noreferrer">source data</a>`
      ).join("<br>");
    }

    function renderChips(output) {
      const wrap = document.getElementById("chipsWrap");
      const chips = document.getElementById("chips");
      const followups = Array.isArray(output.suggested_followups) ? output.suggested_followups : [];
      if (!followups.length) { wrap.hidden = true; return; }
      wrap.hidden = false;
      chips.innerHTML = "";
      for (const prompt of followups.slice(0, 4)) {
        const chip = document.createElement("button");
        chip.className = "qchip";
        chip.type = "button";
        chip.textContent = String(prompt);
        chip.addEventListener("click", () => sendFollowup(String(prompt)));
        chips.appendChild(chip);
      }
    }

    function sendFollowup(prompt) {
      const api = window.openai || {};
      const send = api.sendFollowUpMessage || api.sendFollowupMessage;
      if (typeof send === "function") {
        try { send.call(api, { prompt }); } catch (err) { /* chip stays informational */ }
      }
    }

    function renderFooter(output) {
      const footer = document.getElementById("footer");
      const creditNode = document.getElementById("credit");
      const caveatNode = document.getElementById("caveats");
      const credits = Array.isArray(output.credits) ? output.credits : [];
      const factCites = Array.isArray(output.fact_citations) ? output.fact_citations : [];
      const lines = [];
      const seen = {};
      for (const c of credits) {
        const line = (c && c.credit_line) ? String(c.credit_line) : "";
        if (line && !seen[line]) { seen[line] = true; lines.push("Image credit: " + line); }
      }
      const names = [];
      for (const c of factCites) { if (c && c.title && names.indexOf(c.title) < 0) names.push(String(c.title)); }
      if (names.length) lines.push("Facts from " + names.slice(0, 3).join(", ") + ".");

      const warnings = Array.isArray(output.warnings)
        ? output.warnings.map((w) => (w && w.message) ? w.message : String(w)).filter(Boolean) : [];
      if (!lines.length && !warnings.length) { footer.hidden = true; return; }
      footer.hidden = false;
      creditNode.innerHTML = lines.map(escapeHtml).join("<br>");
      if (warnings.length) {
        caveatNode.hidden = false;
        caveatNode.innerHTML = "<b>Caveats:</b> " + warnings.slice(0, 4).map(escapeHtml).join(" \u00b7 ");
      } else {
        caveatNode.hidden = true;
      }
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


GALLERY_URI = _gallery_uri(GALLERY_HTML)
GALLERY_RESOURCE["uri"] = GALLERY_URI
