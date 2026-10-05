/**
 * SIFWAKU HeatWatch — shared frontend helpers
 * All API calls go to the FastAPI backend; keys never appear here.
 */
const API = "";

async function apiGet(path, params = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, v);
  });
  const url = `${API}${path}${q.toString() ? "?" + q.toString() : ""}`;
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

async function apiPost(path, params = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, v);
  });
  const res = await fetch(`${API}${path}?${q.toString()}`, { method: "POST" });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

function statusBadge(status) {
  const map = {
    AVAILABLE: "badge-green",
    PARTIALLY_AVAILABLE: "badge-yellow",
    UNAVAILABLE: "badge-red",
    AUTHENTICATION_REQUIRED: "badge-orange",
  };
  const icons = {
    AVAILABLE: "🟢",
    PARTIALLY_AVAILABLE: "🟡",
    UNAVAILABLE: "🔴",
    AUTHENTICATION_REQUIRED: "⚠️",
  };
  const cls = map[status] || "badge-blue";
  const icon = icons[status] || "";
  return `<span class="badge ${cls}">${icon} ${status || "UNKNOWN"}</span>`;
}

function riskBadge(level) {
  const map = {
    LOW: "badge-green",
    MODERATE: "badge-yellow",
    HIGH: "badge-orange",
    EXTREME: "badge-red",
  };
  return `<span class="badge ${map[level] || "badge-blue"}">${level || "—"}</span>`;
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmt(v, unit = "") {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return `${Number(v).toFixed(1)}${unit}`;
  return `${v}${unit}`;
}

function exportChartImage(containerId, fileName = "sifwaku-heatwatch-history") {
  const container = document.getElementById(containerId);
  const svg = container && container.querySelector("svg");
  if (!svg) {
    window.alert("No historic chart is available to export.");
    return;
  }

  const sourceViewBox = svg.viewBox.baseVal;
  const chartWidth = sourceViewBox.width || 960;
  const chartHeight = sourceViewBox.height || 410;
  const width = Math.max(960, chartWidth);
  const scale = width / chartWidth;
  const headerHeight = 78;
  const scaledChartHeight = chartHeight * scale;
  const legendItems = [];
  let currentLegend = null;
  const legendSource = container.querySelector(".chart-note");

  if (legendSource) {
    Array.from(legendSource.childNodes).forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE && node.tagName === "SPAN") {
        const style = window.getComputedStyle(node);
        currentLegend = {
          label: "",
          isBar: node.classList.contains("legend-bar"),
          isThreshold: node.classList.contains("analysis-legend-threshold"),
          background: style.backgroundColor,
          borderColor: style.borderTopColor,
          borderStyle: style.borderTopStyle,
        };
        legendItems.push(currentLegend);
      } else if (currentLegend && node.nodeType === Node.TEXT_NODE) {
        currentLegend.label += node.textContent;
      }
    });
  }
  legendItems.forEach((item) => { item.label = item.label.trim(); });

  const legendPositions = [];
  const legendTop = headerHeight + scaledChartHeight + 30;
  let legendX = 28;
  let legendY = legendTop;
  legendItems.forEach((item) => {
    const itemWidth = Math.max(110, item.label.length * 7 + 48);
    if (legendX + itemWidth > width - 28) {
      legendX = 28;
      legendY += 28;
    }
    legendPositions.push({ ...item, x: legendX, y: legendY });
    legendX += itemWidth;
  });
  const height = Math.ceil((legendItems.length ? legendY + 30 : legendTop) + 18);

  const exportSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  exportSvg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  exportSvg.setAttribute("width", String(width));
  exportSvg.setAttribute("height", String(height));
  exportSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const addSvgElement = (parent, name, attributes, text) => {
    const element = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
    if (text !== undefined) element.textContent = text;
    parent.appendChild(element);
    return element;
  };

  addSvgElement(exportSvg, "rect", { x: 0, y: 0, width, height, fill: "#ffffff" });
  addSvgElement(exportSvg, "text", {
    x: 28, y: 31, fill: "#0d4d5b", "font-size": 20, "font-weight": 700,
    "font-family": "Arial, sans-serif",
  }, "SifwakuHeatwatch");
  addSvgElement(exportSvg, "text", {
    x: 28, y: 57, fill: "#31515c", "font-size": 14, "font-weight": 600,
    "font-family": "Arial, sans-serif",
  }, container.querySelector(".chart-title")?.textContent.trim() || "Historical weather chart");

  const chartGroup = addSvgElement(exportSvg, "g", {
    transform: `translate(0 ${headerHeight}) scale(${scale})`,
  });
  const clone = svg.cloneNode(true);
  while (clone.firstChild) chartGroup.appendChild(clone.firstChild);

  legendPositions.forEach((item) => {
    const markerColor = item.background !== "rgba(0, 0, 0, 0)" ? item.background : item.borderColor;
    if (item.isBar) {
      addSvgElement(exportSvg, "rect", {
        x: item.x, y: item.y - 12, width: 12, height: 12, fill: markerColor,
      });
    } else {
      addSvgElement(exportSvg, "line", {
        x1: item.x, y1: item.y - 6, x2: item.x + 22, y2: item.y - 6,
        stroke: markerColor, "stroke-width": item.isThreshold ? 2 : 3,
        "stroke-dasharray": item.isThreshold || item.borderStyle === "dashed" ? "5 3" : "none",
      });
    }
    addSvgElement(exportSvg, "text", {
      x: item.x + 29, y: item.y - 2, fill: "#536873", "font-size": 13,
      "font-family": "Arial, sans-serif",
    }, item.label);
  });

  const wrapper = document.createElement("div");
  wrapper.style.position = "absolute";
  wrapper.style.left = "-9999px";
  wrapper.style.top = "0";
  wrapper.style.width = `${width}px`;
  wrapper.style.height = `${height}px`;
  wrapper.style.overflow = "hidden";
  wrapper.appendChild(exportSvg);
  document.body.appendChild(wrapper);

  const nodes = exportSvg.querySelectorAll("*");
  nodes.forEach((node) => {
    const computed = window.getComputedStyle(node);
    const styleParts = [];
    const fill = computed.fill;
    const stroke = computed.stroke;
    const strokeWidth = computed.strokeWidth;
    const fontSize = computed.fontSize;
    const fontFamily = computed.fontFamily;
    const fontWeight = computed.fontWeight;
    const opacity = computed.opacity;

    if (fill && fill !== "none") styleParts.push(`fill:${fill}`);
    if (stroke && stroke !== "none") styleParts.push(`stroke:${stroke}`);
    if (strokeWidth && strokeWidth !== "0px") styleParts.push(`stroke-width:${strokeWidth}`);
    if (fontSize && fontSize !== "0px") styleParts.push(`font-size:${fontSize}`);
    if (fontFamily) styleParts.push(`font-family:${fontFamily}`);
    if (fontWeight && fontWeight !== "normal") styleParts.push(`font-weight:${fontWeight}`);
    if (opacity && opacity !== "1") styleParts.push(`opacity:${opacity}`);
    if (styleParts.length) node.setAttribute("style", styleParts.join("; "));
  });

  const serialized = new XMLSerializer().serializeToString(exportSvg);
  const blob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const image = new Image();

  image.onload = () => {
    const canvas = document.createElement("canvas");
    const pixelRatio = 2;
    canvas.width = width * pixelRatio;
    canvas.height = height * pixelRatio;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      URL.revokeObjectURL(url);
      wrapper.remove();
      window.alert("The chart could not be exported as an image.");
      return;
    }
    ctx.scale(pixelRatio, pixelRatio);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(image, 0, 0, width, height);

    canvas.toBlob((pngBlob) => {
      if (!pngBlob) {
        URL.revokeObjectURL(url);
        wrapper.remove();
        return;
      }
      const downloadUrl = URL.createObjectURL(pngBlob);
      const link = document.createElement("a");
      link.download = `${fileName}.png`;
      link.href = downloadUrl;
      document.body.appendChild(link);
      link.click();
      window.setTimeout(() => {
        link.remove();
        URL.revokeObjectURL(downloadUrl);
      }, 1000);
      URL.revokeObjectURL(url);
      wrapper.remove();
    }, "image/png");
  };

  image.onerror = () => {
    window.alert("The chart could not be exported as an image.");
    URL.revokeObjectURL(url);
    wrapper.remove();
  };

  image.src = url;
}
