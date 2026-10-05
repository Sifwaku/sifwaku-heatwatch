const historyForm = document.getElementById("analysis-form");
const historyExport = document.getElementById("analysis-export");
let historyObservations = [];

function localDateString(date) {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function setDefaultAnalysisDates() {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - 29);
  document.getElementById("analysis-start").value = localDateString(start);
  document.getElementById("analysis-end").value = localDateString(end);
}

function analysisTemperaturePoints(observations) {
  return observations
    .filter((item) => item.timestamp && item.temperature_c !== null && item.temperature_c !== undefined && item.temperature_c !== "" && Number.isFinite(Number(item.temperature_c)))
    .map((item) => ({
      ...item,
      temperature: Number(item.temperature_c),
      minimum: item.temperature_min_c === null || item.temperature_min_c === undefined || item.temperature_min_c === "" ? null : Number(item.temperature_min_c),
      date: new Date(item.timestamp),
      day: String(item.timestamp).slice(0, 10),
    }))
    .sort((left, right) => left.date - right.date);
}

function percentile(values, percentage) {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const position = (sorted.length - 1) * percentage;
  const lower = Math.floor(position);
  const fraction = position - lower;
  return sorted[lower] + (sorted[Math.min(lower + 1, sorted.length - 1)] - sorted[lower]) * fraction;
}

function summarizeHotSpells(points, threshold) {
  let runs = 0;
  let longest = 0;
  let current = 0;
  let previousDay = null;
  points.forEach((point) => {
    const serialDay = Date.parse(`${point.day}T00:00:00Z`);
    const previousSerialDay = previousDay ? Date.parse(`${previousDay}T00:00:00Z`) : null;
    const consecutive = previousSerialDay !== null && serialDay - previousSerialDay === 86400000;
    if (!consecutive) current = 0;
    if (point.temperature >= threshold) {
      if (current === 0) runs += 1;
      current += 1;
      longest = Math.max(longest, current);
    } else {
      current = 0;
    }
    previousDay = point.day;
  });
  return { runs, longest };
}

function renderMonthlySummary(points, threshold) {
  const months = new Map();
  points.forEach((point) => {
    const monthKey = point.day.slice(0, 7);
    if (!months.has(monthKey)) months.set(monthKey, []);
    months.get(monthKey).push(point);
  });
  const rows = [...months.entries()].map(([monthKey, monthPoints]) => {
    const highs = monthPoints.map((point) => point.temperature);
    const lows = monthPoints.filter((point) => Number.isFinite(point.minimum)).map((point) => point.minimum);
    const rains = monthPoints.filter((point) => point.rainfall_mm !== null && point.rainfall_mm !== undefined && point.rainfall_mm !== "" && Number.isFinite(Number(point.rainfall_mm))).map((point) => Number(point.rainfall_mm));
    const monthLabel = new Date(`${monthKey}-01T00:00:00`).toLocaleDateString([], { month: "long", year: "numeric" });
    const rainTotal = rains.length ? `${rains.reduce((sum, value) => sum + value, 0).toFixed(1)} mm` : "—";
    return `<tr><td>${escapeHtml(monthLabel)}</td><td>${monthPoints.length}</td><td>${(highs.reduce((sum, value) => sum + value, 0) / highs.length).toFixed(1)}°C</td><td>${lows.length ? `${(lows.reduce((sum, value) => sum + value, 0) / lows.length).toFixed(1)}°C` : "—"}</td><td>${highs.filter((value) => value >= threshold).length}</td><td>${rainTotal}</td></tr>`;
  }).join("");
  document.getElementById("monthly-summary").innerHTML = rows || '<tr><td colspan="6">No usable daily values available.</td></tr>';
}

function renderAnalysisMetrics(observations, threshold) {
  const points = analysisTemperaturePoints(observations);
  const expectedDays = Math.max(1, Math.round((Date.parse(`${document.getElementById("analysis-end").value}T00:00:00Z`) - Date.parse(`${document.getElementById("analysis-start").value}T00:00:00Z`)) / 86400000) + 1);
  const temps = points.map((point) => point.temperature);
  const mean = temps.length ? temps.reduce((sum, value) => sum + value, 0) / temps.length : null;
  const hotDays = points.filter((point) => point.temperature >= threshold).length;
  const hotSpells = summarizeHotSpells(points, threshold);
  const lows = points.filter((point) => Number.isFinite(point.minimum)).map((point) => point.minimum);
  const pairedRanges = points.filter((point) => Number.isFinite(point.minimum)).map((point) => point.temperature - point.minimum);
  const rainValues = observations
    .map((item) => item.rainfall_mm)
    .filter((value) => value !== null && value !== undefined && value !== "")
    .map(Number)
    .filter(Number.isFinite);
  const rainTotal = rainValues.length ? rainValues.reduce((sum, value) => sum + value, 0) : null;
  const rainDays = rainValues.filter((value) => value > 0).length;

  document.getElementById("metric-coverage").textContent = `${Math.min(100, points.length / expectedDays * 100).toFixed(0)}%`;
  document.getElementById("metric-days").textContent = `${points.length} of ${expectedDays} days with temperature`;
  document.getElementById("metric-mean-high").textContent = mean === null ? "—" : `${mean.toFixed(1)}°C`;
  document.getElementById("metric-mean-low").textContent = lows.length ? `${(lows.reduce((sum, value) => sum + value, 0) / lows.length).toFixed(1)}°C` : "—";
  document.getElementById("metric-p90").textContent = temps.length ? `${percentile(temps, 0.9).toFixed(1)}°C` : "—";
  document.getElementById("metric-hot").textContent = `${hotDays}`;
  document.getElementById("metric-hot-share").textContent = `${threshold}°C threshold · longest spell ${hotSpells.longest} days · ${hotSpells.runs} spells`;
  document.getElementById("metric-range").textContent = pairedRanges.length ? `${(pairedRanges.reduce((sum, value) => sum + value, 0) / pairedRanges.length).toFixed(1)}°C` : "—";
  document.getElementById("metric-rain").textContent = rainTotal === null ? "—" : `${rainTotal.toFixed(1)} mm`;
  document.getElementById("metric-rain-days").textContent = rainTotal === null ? "No rainfall values available" : `Across ${rainValues.length} days · ${rainDays} rainy days`;

  renderAnalysisChart(points, threshold);
  renderMonthlySummary(points, threshold);
}

function renderAnalysisChart(points, threshold) {
  const chart = document.getElementById("analysis-chart");
  if (points.length < 2) {
    chart.textContent = "No chart shown: at least two usable daily temperature values are required.";
    return;
  }

  const width = 960;
  const height = 410;
  const plot = { left: 68, right: 22, temperatureTop: 34, temperatureBottom: 222, rainTop: 274, rainBottom: 350 };
  const rainfall = points.map((point) => point.rainfall_mm === null || point.rainfall_mm === undefined || point.rainfall_mm === "" || !Number.isFinite(Number(point.rainfall_mm)) ? null : Math.max(0, Number(point.rainfall_mm)));
  const temperatures = points.map((point) => point.temperature);
  const minimums = points.map((point) => point.minimum);
  const dates = points.map((point) => Date.parse(`${point.day}T00:00:00Z`));
  const startTime = dates[0];
  const endTime = dates[dates.length - 1];
  const timeRange = Math.max(86400000, endTime - startTime);
  const xAtTime = (time) => plot.left + (time - startTime) / timeRange * (width - plot.left - plot.right);
  const x = (point) => xAtTime(Date.parse(`${point.day}T00:00:00Z`));
  const niceStep = (value) => {
    const power = 10 ** Math.floor(Math.log10(Math.max(value, 0.0001)));
    const fraction = value / power;
    const factor = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
    return factor * power;
  };
  const tempValues = [...temperatures, ...minimums.filter(Number.isFinite), threshold];
  const tempStep = niceStep((Math.max(...tempValues) - Math.min(...tempValues)) / 4);
  const tempMin = Math.floor(Math.min(...tempValues) / tempStep) * tempStep;
  const tempMax = Math.max(tempMin + tempStep, Math.ceil(Math.max(...tempValues) / tempStep) * tempStep);
  const yTemp = (value) => plot.temperatureBottom - (value - tempMin) / (tempMax - tempMin) * (plot.temperatureBottom - plot.temperatureTop);
  const maxRain = Math.max(...rainfall.filter(Number.isFinite), 0);
  const rainStep = maxRain > 0 ? niceStep(maxRain / 3) : 1;
  const rainAxisMax = Math.max(rainStep, Math.ceil(maxRain / rainStep) * rainStep);
  const yRain = (value) => plot.rainBottom - value / rainAxisMax * (plot.rainBottom - plot.rainTop);
  const barWidth = Math.max(1.5, Math.min(14, (width - plot.left - plot.right) * 86400000 / timeRange * 0.72));
  const bars = rainfall.map((value, index) => {
    if (value === null) return "";
    const pointX = x(points[index]);
    const y = yRain(value);
    return `<rect x="${(pointX - barWidth / 2).toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${(plot.rainBottom - y).toFixed(1)}" class="analysis-rain-bar"><title>${escapeHtml(points[index].day)}: ${value.toFixed(1)} mm</title></rect>`;
  }).join("");
  const seriesPath = (valueFor, scale) => {
    let path = "";
    let previousDay = null;
    points.forEach((point) => {
      const value = valueFor(point);
      if (!Number.isFinite(value)) {
        previousDay = null;
        return;
      }
      const previousTime = previousDay ? Date.parse(`${previousDay}T00:00:00Z`) : null;
      const currentTime = Date.parse(`${point.day}T00:00:00Z`);
      const command = previousTime !== null && currentTime - previousTime === 86400000 ? "L" : "M";
      path += `${command}${x(point).toFixed(1)},${scale(value).toFixed(1)} `;
      previousDay = point.day;
    });
    return path.trim();
  };
  const highPath = seriesPath((point) => point.temperature, yTemp);
  const lowPath = seriesPath((point) => point.minimum, yTemp);
  const dots = points.map((point) => `<circle cx="${x(point).toFixed(1)}" cy="${yTemp(point.temperature).toFixed(1)}" r="2.2" class="analysis-temp-dot"><title>${escapeHtml(point.day)}: high ${point.temperature.toFixed(1)}°C${Number.isFinite(point.minimum) ? `, low ${point.minimum.toFixed(1)}°C` : ""}</title></circle>`).join("");
  const tempGrid = [];
  for (let value = tempMin; value <= tempMax + tempStep / 10; value += tempStep) {
    const position = yTemp(value).toFixed(1);
    tempGrid.push(`<line x1="${plot.left}" x2="${width - plot.right}" y1="${position}" y2="${position}" class="chart-grid" /><text x="${plot.left - 10}" y="${Number(position) + 4}" text-anchor="end" class="chart-label">${value.toFixed(0)}°</text>`);
  }
  const rainGrid = [];
  for (let value = 0; value <= rainAxisMax + rainStep / 10; value += rainStep) {
    const position = yRain(value).toFixed(1);
    const label = value.toFixed(rainStep < 1 ? 1 : 0);
    rainGrid.push(`<line x1="${plot.left}" x2="${width - plot.right}" y1="${position}" y2="${position}" class="chart-grid" /><text x="${plot.left - 10}" y="${Number(position) + 4}" text-anchor="end" class="chart-label">${label}</text>`);
  }
  const spanDays = timeRange / 86400000;
  const desiredTickCount = Math.min(6, Math.max(3, Math.round(spanDays / 10)));
  const tickTimes = [];
  for (let index = 0; index < desiredTickCount; index += 1) {
    const ratio = desiredTickCount === 1 ? 0 : index / (desiredTickCount - 1);
    const value = startTime + (endTime - startTime) * ratio;
    tickTimes.push(value);
  }
  const ticks = [...new Set(tickTimes)].map((time, index) => {
    const date = new Date(time);
    const label = spanDays <= 60
      ? date.toLocaleDateString([], { month: "short", day: "numeric", timeZone: "UTC" })
      : date.toLocaleDateString([], { month: "short", year: "2-digit", timeZone: "UTC" });
    const tickX = xAtTime(time).toFixed(1);
    return `<line x1="${tickX}" x2="${tickX}" y1="${plot.rainBottom}" y2="${plot.rainBottom + 5}" class="chart-axis" /><text x="${tickX}" y="${height - 12}" text-anchor="middle" class="chart-label">${escapeHtml(label)}</text>`;
  }).join("");
  const thresholdY = yTemp(threshold).toFixed(1);
  const rainTitle = rainfall.some(Number.isFinite) ? `RAINFALL (MM/DAY, 0-${rainAxisMax.toFixed(rainStep < 1 ? 1 : 0)})` : "RAINFALL (NO VALUES AVAILABLE)";

  chart.innerHTML = `<div class="chart-title">${points.length} provider-estimated daily records · calendar spacing · separate temperature and rainfall scales</div><div class="chart-note"><span class="legend-line actual"></span>Daily maximum <span class="legend-line average"></span>Daily minimum <span class="analysis-legend-threshold"></span>Selected threshold <span class="legend-bar"></span>Daily rainfall</div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily maximum and minimum temperatures with rainfall on a separate scale"><text x="${plot.left}" y="20" class="analysis-panel-label">TEMPERATURE (°C)</text>${tempGrid.join("")}<line x1="${plot.left}" x2="${width - plot.right}" y1="${thresholdY}" y2="${thresholdY}" class="analysis-threshold" /><path d="${lowPath}" class="analysis-temp-min" /><path d="${highPath}" class="analysis-temp-line" />${dots}<line x1="${plot.left}" x2="${width - plot.right}" y1="${plot.rainTop - 12}" y2="${plot.rainTop - 12}" class="chart-axis" /><text x="${plot.left}" y="${plot.rainTop - 18}" class="analysis-panel-label">${rainTitle}</text>${rainGrid.join("")}${bars}<line x1="${plot.left}" x2="${width - plot.right}" y1="${plot.rainBottom}" y2="${plot.rainBottom}" class="chart-axis" />${ticks}</svg>`;
}

function downloadAnalysisCsv() {
  if (!historyObservations.length) return;
  const columns = ["timestamp", "location", "latitude", "longitude", "temperature_max_c", "temperature_min_c", "humidity_percent", "rainfall_mm", "wind_speed_ms", "source"];
  const location = document.getElementById("analysis-location").value.trim();
  const latitude = document.getElementById("analysis-latitude").value;
  const longitude = document.getElementById("analysis-longitude").value;
  const rows = historyObservations.map((item) => [item.timestamp, location, latitude, longitude, item.temperature_c, item.temperature_min_c, item.humidity_percent, item.rainfall_mm, item.wind_speed_ms, item.source]);
  const csv = [columns, ...rows].map((row) => row.map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `heatwatch-${location.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "") || "history"}-${document.getElementById("analysis-start").value}-to-${document.getElementById("analysis-end").value}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

historyForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.getElementById("analysis-load");
  const status = document.getElementById("analysis-status");
  const startDate = document.getElementById("analysis-start").value;
  const endDate = document.getElementById("analysis-end").value;
  const threshold = Number(document.getElementById("analysis-threshold").value);
  if (startDate > endDate) {
    status.textContent = "The start date must be on or before the end date.";
    return;
  }

  button.disabled = true;
  historyExport.disabled = true;
  status.textContent = "Requesting historical estimates from Open-Meteo...";
  try {
    const data = await apiGet("/api/history", {
      location_name: document.getElementById("analysis-location").value.trim(),
      latitude: Number(document.getElementById("analysis-latitude").value),
      longitude: Number(document.getElementById("analysis-longitude").value),
      start_date: startDate,
      end_date: endDate,
      provider: "Open-Meteo",
      store: true,
    });
    if (!data.ok) throw new Error(data.error || "Historical data unavailable");
    historyObservations = data.observations || [];
    renderAnalysisMetrics(historyObservations, threshold);
    historyExport.disabled = historyObservations.length === 0;
    status.textContent = `${data.count} usable rows from ${data.provider}; ${data.invalid_count || 0} rejected by basic data checks; ${data.stored_count || 0} new rows stored with source and timestamp. These are estimates, not station observations.`;
  } catch (error) {
    historyObservations = [];
    status.textContent = `Historical analysis unavailable: ${error.message}`;
    document.getElementById("analysis-chart").textContent = "No data loaded.";
    renderAnalysisMetrics([], threshold);
  } finally {
    button.disabled = false;
  }
});

document.getElementById("analysis-image-export").addEventListener("click", () => {
  exportChartImage("analysis-chart", "sifwaku-history-analysis");
});

historyExport.addEventListener("click", downloadAnalysisCsv);
document.getElementById("analysis-threshold").addEventListener("change", () => {
  if (historyObservations.length) renderAnalysisMetrics(historyObservations, Number(document.getElementById("analysis-threshold").value));
});
setDefaultAnalysisDates();
