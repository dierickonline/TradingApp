# gui/chart_widget.py
"""Standalone chart window backed by TradingView's Lightweight Charts.

Renders the chart inside a QWebEngineView. We embed an HTML/JS page that
loads the standalone Lightweight Charts bundle from a CDN, then push bars
into it from Python via ``QWebEnginePage.runJavaScript``. The page exposes
several globals — ``setBars(barsJson)`` for the initial load,
``updateBar(barJson)`` for live updates, ``clearBars()`` for switching
timeframes (preserves drawings), and ``setRiskContext(ctx)`` so JS can size
default position quantities the same way the trader widget does.

JS->Python communication uses QWebChannel. ``ChartBridge`` exposes a
``submitBracketOrder(json)`` slot that JS invokes when the user clicks
"Send Orders" in the position panel; ``ChartWindow`` re-emits the parsed
order data to its host (MainWindow) for the actual IB submit.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from PyQt6.QtCore import QObject, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QPushButton,
                             QVBoxLayout, QWidget)

logger = logging.getLogger(__name__)


CHART_HTML = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
    html, body {
        margin: 0;
        padding: 0;
        height: 100%;
        background: #ffffff;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    #main {
        display: flex;
        height: 100%;
    }
    #toolbar {
        width: 48px;
        background: #f5f5f5;
        border-right: 1px solid #ddd;
        display: flex;
        flex-direction: column;
        padding: 6px 0;
        gap: 4px;
        flex-shrink: 0;
    }
    #toolbar button {
        width: 36px;
        height: 36px;
        margin: 0 6px;
        border: 1px solid #ddd;
        background: white;
        border-radius: 4px;
        cursor: pointer;
        font-weight: bold;
        font-size: 16px;
        line-height: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0;
    }
    #toolbar button:hover {
        background: #e8f3ff;
        border-color: #2196F3;
    }
    #toolbar button.active {
        background: #2196F3;
        color: white;
        border-color: #1976D2;
    }
    #toolbar #tool-long       { color: #2e7d32; }
    #toolbar #tool-short      { color: #c62828; }
    #toolbar #tool-hline      { color: #2196F3; }
    #toolbar #tool-pdhl       { color: #2196F3; font-size: 11px; }
    #toolbar #tool-clear      { color: #616161; }
    #toolbar button.active    { color: white; }
    #toolbar .sep {
        height: 1px;
        background: #ddd;
        margin: 4px 6px;
    }
    #chart {
        flex: 1;
        height: 100%;
        position: relative;
    }
    #chart.placing {
        cursor: crosshair;
    }
    #loading {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        color: #666;
        font-size: 14px;
    }

    /* Position panel */
    #position-panel {
        position: absolute;
        top: 12px;
        left: 12px;
        width: 220px;
        background: white;
        border: 1px solid #ddd;
        border-radius: 6px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.15);
        padding: 10px 12px 12px 12px;
        font-size: 12px;
        z-index: 100;
        display: none;
    }
    .panel-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
    }
    .badge {
        color: white;
        padding: 2px 8px;
        border-radius: 3px;
        font-weight: bold;
        font-size: 11px;
        letter-spacing: 1px;
    }
    #position-panel.long  .badge { background: #2e7d32; }
    #position-panel.short .badge { background: #c62828; }
    .close-btn {
        background: none;
        border: none;
        cursor: pointer;
        font-size: 16px;
        color: #999;
        padding: 0 4px;
        line-height: 1;
    }
    .close-btn:hover { color: #333; }
    .input-row {
        display: flex;
        align-items: center;
        margin: 4px 0;
    }
    .input-row label {
        width: 56px;
        color: #444;
    }
    .input-row input {
        flex: 1;
        border: 1px solid #ddd;
        border-radius: 3px;
        padding: 4px 6px;
        font-size: 12px;
        text-align: right;
        font-family: "Consolas", "Menlo", monospace;
    }
    .input-row input:focus {
        outline: none;
        border-color: #2196F3;
    }
    .input-row input.armed {
        border-color: #ff9800;
        box-shadow: 0 0 0 2px rgba(255, 152, 0, 0.25);
        background: #fff8e1;
    }
    #chart.picking { cursor: crosshair; }
    #chart.dragging-line { cursor: ns-resize; }
    #position-pick-hint {
        display: none;
        margin: 4px 0 0 0;
        padding: 4px 6px;
        background: #fff3e0;
        border: 1px solid #ffcc80;
        border-radius: 3px;
        color: #e65100;
        font-size: 11px;
        text-align: center;
    }
    #position-pick-hint.visible { display: block; }
    .metrics {
        margin: 8px 0 4px 0;
        padding: 6px 8px;
        background: #f5f5f5;
        border-radius: 3px;
        color: #555;
        font-size: 11px;
        font-family: "Consolas", "Menlo", monospace;
    }
    .error {
        color: #c62828;
        font-size: 11px;
        min-height: 14px;
        margin: 2px 0 6px 0;
    }
    .send-btn {
        width: 100%;
        background: #2196F3;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 7px;
        font-weight: bold;
        cursor: pointer;
        font-size: 12px;
    }
    .send-btn:hover { background: #1976D2; }
    .send-btn:disabled {
        background: #cccccc;
        cursor: not-allowed;
    }
</style>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
</head>
<body>
<div id="main">
    <div id="toolbar">
        <button id="tool-long" title="Long position — click to arm, then click on the chart at your entry price">▲</button>
        <button id="tool-short" title="Short position — click to arm, then click on the chart at your entry price">▼</button>
        <div class="sep"></div>
        <button id="tool-hline" title="Horizontal line">─</button>
        <button id="tool-pdhl" title="Previous day high/low — toggle blue lines">PD</button>
        <div class="sep"></div>
        <button id="tool-clear" title="Remove all drawings">✕</button>
    </div>
    <div id="chart">
        <div id="loading">Waiting for bars…</div>
        <div id="position-panel">
            <div class="panel-header">
                <span class="badge" id="position-badge">LONG</span>
                <button class="close-btn" id="position-cancel" title="Cancel">×</button>
            </div>
            <div class="input-row">
                <label for="entry-input">Entry</label>
                <input type="number" id="entry-input" step="0.01">
            </div>
            <div class="input-row">
                <label for="stop-input">Stop</label>
                <input type="number" id="stop-input" step="0.01">
            </div>
            <div class="input-row">
                <label for="target-input">Target</label>
                <input type="number" id="target-input" step="0.01">
            </div>
            <div class="input-row">
                <label for="qty-input">Qty</label>
                <input type="number" id="qty-input" step="1" min="1">
            </div>
            <div class="metrics" id="position-metrics">R/R: —</div>
            <div id="position-pick-hint">Click on the chart to set price · Esc to cancel</div>
            <div class="error" id="position-error"></div>
            <button class="send-btn" id="send-orders-btn">Send Orders</button>
        </div>
    </div>
</div>
<script>
let chart = null;
let candleSeries = null;
let lastTime = 0;
let placementMode = null;     // 'hline' | 'long' | 'short' | null
let armedPriceField = null;   // id of price input awaiting a chart click ('entry-input' | 'stop-input' | 'target-input')
let bridge = null;
let activePosition = null;    // {type, entryPrice, stopPrice, targetPrice, quantity, entryLine, stopLine, targetLine}
const priceLines = [];        // standalone horizontal lines (separate from active position)
let allBars = [];             // mirror of candleSeries data, for prev-day H/L
let pdhlLines = [];           // blue lines for previous day's high/low (toggled by 'PD' button)
const PICK_FIELD_IDS = ['entry-input', 'stop-input', 'target-input'];
const DRAG_THRESHOLD_PX = 6;
let hoveredLine = null;       // 'entry' | 'stop' | 'target' | null
let draggedLine = null;       // same; non-null means a drag is in progress
let dragStartPrice = null;    // price at drag start, used for Esc-revert
let savedChartHandlers = null;// chart pan/scale options snapshotted during drag
let riskContext = { available_funds: 0, max_risk_percentage: 2.0, risk_reward_ratio: 2.0 };

// QWebChannel setup -- bridge becomes available when the channel is ready.
new QWebChannel(qt.webChannelTransport, function(channel) {
    bridge = channel.objects.bridge;
});

window.setRiskContext = function(ctx) {
    if (ctx && typeof ctx === 'object') {
        riskContext = Object.assign({}, riskContext, ctx);
    }
};

function initChart() {
    const container = document.getElementById('chart');
    chart = LightweightCharts.createChart(container, {
        layout: { background: { color: '#ffffff' }, textColor: '#333' },
        grid: {
            vertLines: { color: '#eee' },
            horzLines: { color: '#eee' },
        },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#ccc' },
        timeScale: {
            borderColor: '#ccc',
            timeVisible: true,
            secondsVisible: false,
        },
    });
    candleSeries = chart.addCandlestickSeries({
        upColor: '#4CAF50',
        downColor: '#f44336',
        borderUpColor: '#4CAF50',
        borderDownColor: '#f44336',
        wickUpColor: '#4CAF50',
        wickDownColor: '#f44336',
    });

    chart.subscribeClick(handleChartClick);

    container.addEventListener('mousemove', onChartHoverForDrag);
    // Capture phase so we beat LWC's own mousedown handler that would start a pan.
    container.addEventListener('mousedown', onChartMouseDownForDrag, true);

    const ro = new ResizeObserver(() => {
        chart.applyOptions({
            width: container.clientWidth,
            height: container.clientHeight,
        });
    });
    ro.observe(container);

    container.addEventListener('wheel', handlePriceAxisWheel,
        { passive: false, capture: true });
}

function handlePriceAxisWheel(e) {
    if (!chart) return;
    const container = document.getElementById('chart');
    const rect = container.getBoundingClientRect();
    const priceScaleWidth = Math.max(chart.priceScale('right').width(), 40);
    const overPriceAxis = e.clientX >= rect.right - priceScaleWidth
        && e.clientX <= rect.right
        && e.clientY >= rect.top
        && e.clientY <= rect.bottom;
    if (!overPriceAxis) return;

    e.preventDefault();
    e.stopPropagation();

    const ps = chart.priceScale('right');
    const cur = ps.options().scaleMargins || { top: 0.1, bottom: 0.1 };
    const step = 0.04;
    let newTop;
    let newBottom;
    if (e.deltaY < 0) {
        newTop = Math.max(0, cur.top - step);
        newBottom = Math.max(0, cur.bottom - step);
    } else {
        newTop = Math.min(0.45, cur.top + step);
        newBottom = Math.min(0.45, cur.bottom + step);
    }
    if (newTop === cur.top && newBottom === cur.bottom) return;
    ps.applyOptions({ scaleMargins: { top: newTop, bottom: newBottom } });
}

// --- chart click dispatch ---------------------------------------------------

function handleChartClick(param) {
    if (!param || !param.point) return;
    const price = candleSeries.coordinateToPrice(param.point.y);
    if (price === null || price === undefined) return;

    if (armedPriceField) {
        const input = document.getElementById(armedPriceField);
        if (input) {
            input.value = price.toFixed(2);
            // Fire change so applyInputsToPosition() runs and the price line moves.
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
        clearArmedField();
        return;
    }

    if (placementMode === 'hline') {
        const line = candleSeries.createPriceLine({
            price: price,
            color: '#2196F3',
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: '',
        });
        priceLines.push(line);
        setPlacementMode(null);
    } else if (placementMode === 'long' || placementMode === 'short') {
        createPosition(placementMode, price);
        setPlacementMode(null);
    }
}

function setPlacementMode(mode) {
    placementMode = mode;
    document.querySelectorAll('#toolbar button').forEach(b => b.classList.remove('active'));
    const chartEl = document.getElementById('chart');
    chartEl.classList.toggle('placing', mode !== null);
    if (mode === 'hline') {
        document.getElementById('tool-hline').classList.add('active');
    } else if (mode === 'long') {
        document.getElementById('tool-long').classList.add('active');
    } else if (mode === 'short') {
        document.getElementById('tool-short').classList.add('active');
    }
    if (mode !== null) {
        clearArmedField();
        cancelDrag();
    }
}

function armPriceField(id) {
    if (armedPriceField === id) return;
    clearArmedField();
    armedPriceField = id;
    const input = document.getElementById(id);
    if (input) input.classList.add('armed');
    document.getElementById('chart').classList.add('picking');
    document.getElementById('position-pick-hint').classList.add('visible');
}

function clearArmedField() {
    if (armedPriceField) {
        const input = document.getElementById(armedPriceField);
        if (input) input.classList.remove('armed');
    }
    armedPriceField = null;
    document.getElementById('chart').classList.remove('picking');
    document.getElementById('position-pick-hint').classList.remove('visible');
}

// --- line dragging ---------------------------------------------------------

function findPositionLineNearY(y) {
    if (!activePosition) return null;
    const targets = [
        ['entry',  activePosition.entryPrice],
        ['stop',   activePosition.stopPrice],
        ['target', activePosition.targetPrice],
    ];
    let best = null;
    let bestDist = DRAG_THRESHOLD_PX;
    for (const [key, price] of targets) {
        const ly = candleSeries.priceToCoordinate(price);
        if (ly === null || ly === undefined) continue;
        const d = Math.abs(y - ly);
        if (d <= bestDist) {
            best = key;
            bestDist = d;
        }
    }
    return best;
}

function setLinePrice(which, price) {
    if (!activePosition || !(price > 0)) return;
    if (which === 'entry') {
        activePosition.entryPrice = price;
        activePosition.entryLine.applyOptions({ price: price });
        document.getElementById('entry-input').value = price.toFixed(2);
    } else if (which === 'stop') {
        activePosition.stopPrice = price;
        activePosition.stopLine.applyOptions({ price: price });
        document.getElementById('stop-input').value = price.toFixed(2);
    } else if (which === 'target') {
        activePosition.targetPrice = price;
        activePosition.targetLine.applyOptions({ price: price });
        document.getElementById('target-input').value = price.toFixed(2);
    }
    // Resize so dollar-risk stays at max_risk_percentage of available funds.
    // Target drag is a no-op here (entry/stop unchanged → same qty).
    const newQty = computeDefaultQuantity(activePosition.entryPrice, activePosition.stopPrice);
    activePosition.quantity = newQty;
    document.getElementById('qty-input').value = newQty;
    refreshMetricsAndValidation();
}

function isOverChartArea(e) {
    // Skip events on the position panel (they bubble to the chart container).
    if (e.target && e.target.closest && e.target.closest('#position-panel')) return false;
    const rect = document.getElementById('chart').getBoundingClientRect();
    const x = e.clientX - rect.left;
    if (x < 0 || x > rect.width) return false;
    const psWidth = chart.priceScale('right').width();
    // Stay clear of the right-side price axis to avoid hijacking its wheel/pan.
    return x <= rect.width - psWidth;
}

function onChartHoverForDrag(e) {
    if (draggedLine) return;
    if (placementMode || armedPriceField) {
        if (hoveredLine) {
            hoveredLine = null;
            document.getElementById('chart').classList.remove('dragging-line');
        }
        return;
    }
    if (!activePosition || !isOverChartArea(e)) {
        if (hoveredLine) {
            hoveredLine = null;
            document.getElementById('chart').classList.remove('dragging-line');
        }
        return;
    }
    const rect = document.getElementById('chart').getBoundingClientRect();
    const y = e.clientY - rect.top;
    const found = findPositionLineNearY(y);
    if (found !== hoveredLine) {
        hoveredLine = found;
        document.getElementById('chart').classList.toggle('dragging-line', !!found);
    }
}

function onChartMouseDownForDrag(e) {
    if (e.button !== 0) return; // left button only
    if (placementMode || armedPriceField) return;
    if (!activePosition || !isOverChartArea(e)) return;
    const rect = document.getElementById('chart').getBoundingClientRect();
    const y = e.clientY - rect.top;
    const found = findPositionLineNearY(y);
    if (!found) return;

    e.preventDefault();
    e.stopPropagation();
    draggedLine = found;
    dragStartPrice = activePosition[found + 'Price'];
    // Suppress LWC's pan/scale gestures during the drag so the chart doesn't slide.
    const opts = chart.options();
    savedChartHandlers = {
        handleScroll: opts.handleScroll,
        handleScale: opts.handleScale,
    };
    chart.applyOptions({ handleScroll: false, handleScale: false });
    document.addEventListener('mousemove', onDragMove);
    document.addEventListener('mouseup', onDragEnd);
}

function onDragMove(e) {
    if (!draggedLine || !activePosition) return;
    const rect = document.getElementById('chart').getBoundingClientRect();
    const y = e.clientY - rect.top;
    const newPrice = candleSeries.coordinateToPrice(y);
    if (newPrice === null || newPrice === undefined || !(newPrice > 0)) return;
    setLinePrice(draggedLine, newPrice);
}

function onDragEnd(e) {
    if (!draggedLine) return;
    cancelDrag();
}

function cancelDrag() {
    if (!draggedLine && !savedChartHandlers) return;
    draggedLine = null;
    dragStartPrice = null;
    document.removeEventListener('mousemove', onDragMove);
    document.removeEventListener('mouseup', onDragEnd);
    if (savedChartHandlers) {
        chart.applyOptions(savedChartHandlers);
        savedChartHandlers = null;
    }
    hoveredLine = null;
    document.getElementById('chart').classList.remove('dragging-line');
}

// --- standalone horizontal lines -------------------------------------------

function clearAllDrawings() {
    while (priceLines.length) {
        const line = priceLines.pop();
        try { candleSeries.removePriceLine(line); } catch (e) { /* ignore */ }
    }
    removePrevDayHighLow();
    removeActivePosition();
}

// --- previous day high/low -------------------------------------------------

function computePrevDayHighLow() {
    if (!allBars.length) return null;
    // Group bars by local-date string. Map preserves insertion order, and
    // since allBars is time-sorted, keys come out chronologically.
    const byDay = new Map();
    for (const bar of allBars) {
        const key = new Date(bar.time * 1000).toDateString();
        let arr = byDay.get(key);
        if (!arr) { arr = []; byDay.set(key, arr); }
        arr.push(bar);
    }
    const keys = Array.from(byDay.keys());
    if (keys.length < 2) return null;
    const prevBars = byDay.get(keys[keys.length - 2]);
    let high = -Infinity, low = Infinity;
    for (const b of prevBars) {
        if (b.high > high) high = b.high;
        if (b.low  < low)  low  = b.low;
    }
    return { high: high, low: low };
}

function removePrevDayHighLow() {
    while (pdhlLines.length) {
        const line = pdhlLines.pop();
        try { candleSeries.removePriceLine(line); } catch (e) { /* ignore */ }
    }
    document.getElementById('tool-pdhl').classList.remove('active');
}

function togglePrevDayHighLow() {
    if (pdhlLines.length) {
        removePrevDayHighLow();
        return;
    }
    const r = computePrevDayHighLow();
    if (!r) return;
    pdhlLines.push(candleSeries.createPriceLine({
        price: r.high,
        color: '#2196F3',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Solid,
        axisLabelVisible: true,
        title: 'PDH',
    }));
    pdhlLines.push(candleSeries.createPriceLine({
        price: r.low,
        color: '#2196F3',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Solid,
        axisLabelVisible: true,
        title: 'PDL',
    }));
    document.getElementById('tool-pdhl').classList.add('active');
}

// --- position drawing ------------------------------------------------------

function createPosition(type, entryPrice) {
    if (activePosition) removeActivePosition();
    const isLong = type === 'long';

    const stopPct = 0.01;
    const rr = (riskContext.risk_reward_ratio && riskContext.risk_reward_ratio > 0)
        ? riskContext.risk_reward_ratio : 2.0;
    const stopPrice = isLong ? entryPrice * (1 - stopPct) : entryPrice * (1 + stopPct);
    const risk = Math.abs(entryPrice - stopPrice);
    const targetPrice = isLong ? entryPrice + risk * rr : entryPrice - risk * rr;
    const quantity = computeDefaultQuantity(entryPrice, stopPrice);

    activePosition = {
        type: type,
        entryPrice: entryPrice,
        stopPrice: stopPrice,
        targetPrice: targetPrice,
        quantity: quantity,
        entryLine: null,
        stopLine: null,
        targetLine: null,
    };

    activePosition.entryLine = candleSeries.createPriceLine({
        price: entryPrice,
        color: isLong ? '#1565c0' : '#1565c0',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Solid,
        axisLabelVisible: true,
        title: isLong ? 'BUY' : 'SELL',
    });
    activePosition.stopLine = candleSeries.createPriceLine({
        price: stopPrice,
        color: '#c62828',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'Stop',
    });
    activePosition.targetLine = candleSeries.createPriceLine({
        price: targetPrice,
        color: '#2e7d32',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'Target',
    });

    showPositionPanel();
}

function removeActivePosition() {
    if (!activePosition) return;
    cancelDrag();
    try { candleSeries.removePriceLine(activePosition.entryLine); } catch(e){}
    try { candleSeries.removePriceLine(activePosition.stopLine); } catch(e){}
    try { candleSeries.removePriceLine(activePosition.targetLine); } catch(e){}
    activePosition = null;
    hidePositionPanel();
}

function computeDefaultQuantity(entry, stop) {
    const riskPerShare = Math.abs(entry - stop);
    if (riskPerShare <= 0 || entry <= 0) return 1;
    if (!riskContext.available_funds || riskContext.available_funds <= 0) return 1;
    const maxRiskAmount = riskContext.available_funds *
        ((riskContext.max_risk_percentage || 2.0) / 100.0);
    const byRisk = Math.floor(maxRiskAmount / riskPerShare);
    const byFunds = Math.floor(riskContext.available_funds / entry);
    const q = Math.min(byRisk, byFunds);
    return Math.max(1, q);
}

// --- position panel --------------------------------------------------------

function showPositionPanel() {
    if (!activePosition) return;
    const panel = document.getElementById('position-panel');
    panel.classList.remove('long', 'short');
    panel.classList.add(activePosition.type);
    // Set 'block' explicitly — clearing the inline style would let the
    // CSS `display: none` rule take effect again.
    panel.style.display = 'block';

    document.getElementById('position-badge').textContent =
        activePosition.type === 'long' ? 'LONG' : 'SHORT';
    document.getElementById('entry-input').value = activePosition.entryPrice.toFixed(2);
    document.getElementById('stop-input').value = activePosition.stopPrice.toFixed(2);
    document.getElementById('target-input').value = activePosition.targetPrice.toFixed(2);
    document.getElementById('qty-input').value = activePosition.quantity;
    document.getElementById('position-error').textContent = '';
    refreshMetricsAndValidation();
}

function hidePositionPanel() {
    clearArmedField();
    document.getElementById('position-panel').style.display = 'none';
}

function applyInputsToPosition() {
    if (!activePosition) return;
    const e = parseFloat(document.getElementById('entry-input').value);
    const s = parseFloat(document.getElementById('stop-input').value);
    const t = parseFloat(document.getElementById('target-input').value);
    const q = parseInt(document.getElementById('qty-input').value, 10);

    if (!isNaN(e) && e > 0 && e !== activePosition.entryPrice) {
        activePosition.entryPrice = e;
        activePosition.entryLine.applyOptions({ price: e });
    }
    if (!isNaN(s) && s > 0 && s !== activePosition.stopPrice) {
        activePosition.stopPrice = s;
        activePosition.stopLine.applyOptions({ price: s });
    }
    if (!isNaN(t) && t > 0 && t !== activePosition.targetPrice) {
        activePosition.targetPrice = t;
        activePosition.targetLine.applyOptions({ price: t });
    }
    if (!isNaN(q) && q > 0) {
        activePosition.quantity = q;
    }
    refreshMetricsAndValidation();
}

function refreshMetricsAndValidation() {
    if (!activePosition) return;
    const risk = Math.abs(activePosition.entryPrice - activePosition.stopPrice);
    const reward = Math.abs(activePosition.targetPrice - activePosition.entryPrice);
    const rr = risk > 0 ? (reward / risk) : 0;
    const dollarRisk = (risk * activePosition.quantity);
    const dollarReward = (reward * activePosition.quantity);
    document.getElementById('position-metrics').textContent =
        `R/R ${rr.toFixed(2)}  ·  Risk $${dollarRisk.toFixed(2)}  ·  Reward $${dollarReward.toFixed(2)}`;

    const isLong = activePosition.type === 'long';
    let valid = true;
    let msg = '';
    const e = activePosition.entryPrice;
    const s = activePosition.stopPrice;
    const t = activePosition.targetPrice;
    if (!(e > 0) || !(s > 0) || !(t > 0)) {
        valid = false; msg = 'Prices must be positive';
    } else if (isLong && s >= e) {
        valid = false; msg = 'Long: stop must be below entry';
    } else if (isLong && t <= e) {
        valid = false; msg = 'Long: target must be above entry';
    } else if (!isLong && s <= e) {
        valid = false; msg = 'Short: stop must be above entry';
    } else if (!isLong && t >= e) {
        valid = false; msg = 'Short: target must be below entry';
    } else if (!(activePosition.quantity > 0)) {
        valid = false; msg = 'Quantity must be > 0';
    }
    document.getElementById('position-error').textContent = msg;
    document.getElementById('send-orders-btn').disabled = !valid;
    return valid;
}

function submitOrders() {
    if (!activePosition) return;
    if (!refreshMetricsAndValidation()) return;
    if (!bridge) {
        document.getElementById('position-error').textContent = 'Bridge not ready';
        return;
    }
    const data = {
        action: activePosition.type === 'long' ? 'BUY' : 'SELL',
        entry: activePosition.entryPrice,
        stop: activePosition.stopPrice,
        target: activePosition.targetPrice,
        quantity: activePosition.quantity,
    };
    try {
        bridge.submitBracketOrder(JSON.stringify(data));
    } catch (e) {
        document.getElementById('position-error').textContent = 'Submit failed: ' + e;
    }
}

// --- toolbar wiring --------------------------------------------------------

document.getElementById('tool-long').addEventListener('click', () => {
    setPlacementMode(placementMode === 'long' ? null : 'long');
});
document.getElementById('tool-short').addEventListener('click', () => {
    setPlacementMode(placementMode === 'short' ? null : 'short');
});
document.getElementById('tool-hline').addEventListener('click', () => {
    setPlacementMode(placementMode === 'hline' ? null : 'hline');
});
document.getElementById('tool-pdhl').addEventListener('click', () => {
    setPlacementMode(null);
    togglePrevDayHighLow();
});
document.getElementById('tool-clear').addEventListener('click', () => {
    setPlacementMode(null);
    clearAllDrawings();
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        if (draggedLine) {
            // Revert to where the drag started, then end it.
            setLinePrice(draggedLine, dragStartPrice);
            cancelDrag();
        }
        setPlacementMode(null);
        clearArmedField();
    }
});

// Panel input wiring -- 'change' fires on blur or Enter, avoiding jitter while typing.
['entry-input', 'stop-input', 'target-input', 'qty-input'].forEach(id => {
    document.getElementById(id).addEventListener('change', applyInputsToPosition);
});

// Focus on a price field arms it; the next chart click writes the price.
// Blur clears with a small delay so the chart click handler can still read
// armedPriceField (blur fires on mousedown, before the click handler runs).
PICK_FIELD_IDS.forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('focus', () => armPriceField(id));
    el.addEventListener('blur', () => {
        setTimeout(() => {
            if (armedPriceField === id && document.activeElement !== el) {
                clearArmedField();
            }
        }, 200);
    });
});
document.getElementById('position-cancel').addEventListener('click', removeActivePosition);
document.getElementById('send-orders-btn').addEventListener('click', submitOrders);

// --- bar push API ---------------------------------------------------------

window.setBars = function(barsJson) {
    if (!chart) initChart();
    const bars = JSON.parse(barsJson);
    candleSeries.setData(bars);
    allBars = bars.slice();
    if (bars.length > 0) {
        lastTime = bars[bars.length - 1].time;
    }
    document.getElementById('loading').style.display = 'none';
    // If PDH/PDL was on for the previous timeframe, recompute on the new data.
    if (pdhlLines.length) {
        removePrevDayHighLow();
        togglePrevDayHighLow();
    }
};

window.updateBar = function(barJson) {
    if (!candleSeries) return;
    const bar = JSON.parse(barJson);
    if (bar.time < lastTime) return;
    candleSeries.update(bar);
    if (allBars.length && allBars[allBars.length - 1].time === bar.time) {
        allBars[allBars.length - 1] = bar;
    } else {
        allBars.push(bar);
    }
    lastTime = bar.time;
};

window.clearBars = function() {
    if (!candleSeries) return;
    candleSeries.setData([]);
    allBars = [];
    lastTime = 0;
    document.getElementById('loading').style.display = '';
};

initChart();
</script>
</body>
</html>
"""


# (label, IB bar size, IB duration). Order is the visual order in the header.
TIMEFRAMES = [
    ("1d", "1 day", "1 Y"),
    ("5m", "5 mins", "5 D"),
    ("1m", "1 min", "2 D"),
]


class ChartBridge(QObject):
    """JS-side bridge object exposed via QWebChannel.

    Methods called from JS (with @pyqtSlot) re-emit a Qt signal so the
    owning ChartWindow can react on the GUI thread without coupling the
    bridge to the window's internals.
    """

    submit_requested = pyqtSignal(dict)  # parsed order dict from JS

    @pyqtSlot(str)
    def submitBracketOrder(self, order_json: str) -> None:
        try:
            data = json.loads(order_json)
        except Exception as e:
            logger.error(f"submitBracketOrder: invalid JSON: {e}")
            return
        if not isinstance(data, dict):
            logger.error(f"submitBracketOrder: expected object, got {type(data).__name__}")
            return
        self.submit_requested.emit(data)


class ChartWindow(QMainWindow):
    """Top-level window that displays a candlestick chart with timeframe toggle.

    The window owns its IB request lifecycle and a per-window QWebChannel
    used to hear order submissions from the embedded position panel. The
    risk context (available funds, max risk %, R/R) is snapshotted at open
    time and pushed to the JS side so the position-sizing default matches
    the trader widget.
    """

    closed = pyqtSignal(object)
    submit_bracket_order = pyqtSignal(dict)  # forwarded to MainWindow

    def __init__(self, ticker: str, historical_data_manager, parent=None,
                 bar_size: str = "5 mins", duration: str = "5 D",
                 available_funds: float = 0.0,
                 max_risk_percentage: float = 2.0,
                 risk_reward_ratio: float = 2.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._ticker = ticker.upper()
        self._historical_data_manager = historical_data_manager
        self._req_id: Optional[int] = None
        self._page_loaded = False
        self._pending_bars: Optional[list] = None
        self._pending_updates: list = []
        self._current_bar_size: Optional[str] = None
        self._tf_buttons: dict = {}
        self._risk_context = {
            'available_funds': float(available_funds),
            'max_risk_percentage': float(max_risk_percentage),
            'risk_reward_ratio': float(risk_reward_ratio),
        }

        self.setWindowTitle(f"{self._ticker} chart")
        self.resize(1200, 720)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())

        self.web_view = QWebEngineView()
        self.web_view.loadFinished.connect(self._on_page_loaded)
        layout.addWidget(self.web_view)

        # Set up the JS<->Python bridge BEFORE setHtml so qt.webChannelTransport
        # is available by the time the page's QWebChannel constructor runs.
        self.bridge = ChartBridge()
        self.bridge.submit_requested.connect(self._on_submit_requested)
        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject('bridge', self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        # baseUrl=https lets the unpkg <script> tag resolve over the network;
        # qrc:///qtwebchannel/qwebchannel.js still loads alongside it.
        self.web_view.setHtml(CHART_HTML, QUrl("https://localhost/"))

        self._historical_data_manager.chart_bars_received.connect(self._on_chart_bars)
        self._historical_data_manager.chart_bar_updated.connect(self._on_chart_bar_update)
        self._historical_data_manager.historical_data_error.connect(self._on_chart_error)

        match = next(((bs, d) for _, bs, d in TIMEFRAMES if bs == bar_size), None)
        if match is None:
            match = (bar_size, duration)
        self.set_timeframe(*match)

    # -- header ------------------------------------------------------------

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(38)
        header.setStyleSheet(
            "QWidget { background: #f5f5f5; border-bottom: 1px solid #ddd; }"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(14, 4, 14, 4)
        h.setSpacing(8)

        self.ticker_label = QLabel(self._ticker)
        self.ticker_label.setStyleSheet(
            "color: #333; font-weight: bold; font-size: 15px; border: none;"
        )
        h.addWidget(self.ticker_label)
        h.addSpacing(12)

        for label, bar_size, duration in TIMEFRAMES:
            btn = QPushButton(label)
            btn.setFixedSize(40, 26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._tf_button_qss(selected=False))
            btn.clicked.connect(
                lambda _checked=False, bs=bar_size, d=duration: self.set_timeframe(bs, d)
            )
            h.addWidget(btn)
            self._tf_buttons[bar_size] = btn

        h.addStretch()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "color: #666; font-style: italic; font-size: 13px; border: none;"
        )
        h.addWidget(self.status_label)
        return header

    @staticmethod
    def _tf_button_qss(selected: bool) -> str:
        if selected:
            return """
                QPushButton {
                    background: #2196F3;
                    color: white;
                    border: 1px solid #1976D2;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 12px;
                }
                QPushButton:hover { background: #1E88E5; }
            """
        return """
            QPushButton {
                background: white;
                color: #2196F3;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #e3f2fd;
                border-color: #2196F3;
            }
        """

    def _refresh_tf_buttons(self):
        for bs, btn in self._tf_buttons.items():
            btn.setStyleSheet(self._tf_button_qss(selected=(bs == self._current_bar_size)))

    # -- timeframe ---------------------------------------------------------

    def set_timeframe(self, bar_size: str, duration: str):
        if bar_size == self._current_bar_size:
            return

        if self._req_id is not None:
            try:
                self._historical_data_manager.cancel_chart_request(self._req_id)
            except Exception as e:
                logger.error(f"Error cancelling chart request: {e}")
            self._req_id = None
        self._pending_bars = None
        self._pending_updates.clear()

        self._current_bar_size = bar_size
        self._refresh_tf_buttons()
        self.setWindowTitle(f"{self._ticker} · {bar_size} chart")
        self.status_label.setText("Loading…")

        if self._page_loaded:
            self.web_view.page().runJavaScript("window.clearBars && window.clearBars();")

        self._historical_data_manager.request_chart_bars(
            self._ticker, bar_size=bar_size, duration=duration,
            callback=self._on_request_submitted,
        )

    # -- risk context ------------------------------------------------------

    def update_risk_context(self, *, available_funds: Optional[float] = None,
                            max_risk_percentage: Optional[float] = None,
                            risk_reward_ratio: Optional[float] = None) -> None:
        """Update the JS-side risk context. Called when the trader widget's
        funds or risk parameters change after the chart was opened."""
        if available_funds is not None:
            self._risk_context['available_funds'] = float(available_funds)
        if max_risk_percentage is not None:
            self._risk_context['max_risk_percentage'] = float(max_risk_percentage)
        if risk_reward_ratio is not None:
            self._risk_context['risk_reward_ratio'] = float(risk_reward_ratio)
        if self._page_loaded:
            self._push_risk_context()

    def _push_risk_context(self) -> None:
        js = (f"window.setRiskContext && "
              f"window.setRiskContext({json.dumps(self._risk_context)});")
        self.web_view.page().runJavaScript(js)

    # -- lifecycle ---------------------------------------------------------

    def _on_request_submitted(self, req_id: Optional[int], error: Optional[str]):
        if error:
            self.status_label.setText(f"Error: {error}")
            return
        self._req_id = req_id
        logger.debug(f"Chart {self._ticker} {self._current_bar_size} req_id={req_id}")

    def _on_submit_requested(self, order_data: dict):
        """Forward the JS-submitted order to the host with the chart's ticker
        attached. Validation is left to the host (which can also surface a
        Qt confirmation before submitting to IB)."""
        order_data = dict(order_data)
        order_data['ticker'] = self._ticker
        order_data['entry_order_type'] = 'LMT'
        self.submit_bracket_order.emit(order_data)

    def closeEvent(self, event):
        try:
            if self._req_id is not None:
                self._historical_data_manager.cancel_chart_request(self._req_id)
        except Exception as e:
            logger.error(f"Error cancelling chart request on close: {e}")
        try:
            self._historical_data_manager.chart_bars_received.disconnect(self._on_chart_bars)
            self._historical_data_manager.chart_bar_updated.disconnect(self._on_chart_bar_update)
            self._historical_data_manager.historical_data_error.disconnect(self._on_chart_error)
        except (TypeError, RuntimeError):
            pass
        self.closed.emit(self)
        super().closeEvent(event)

    # -- page <-> data -----------------------------------------------------

    def _on_page_loaded(self, ok: bool):
        self._page_loaded = bool(ok)
        if not ok:
            logger.error(f"Chart page failed to load for {self._ticker}")
            return
        self._push_risk_context()
        if self._pending_bars is not None:
            self._push_bars(self._pending_bars)
            self._pending_bars = None
        for bar in self._pending_updates:
            self._push_update(bar)
        self._pending_updates.clear()

    def _on_chart_bars(self, req_id: int, ticker: str, bars: list):
        if req_id != self._req_id:
            return
        if self._page_loaded:
            self._push_bars(bars)
        else:
            self._pending_bars = bars
        self.status_label.setText(f"{len(bars)} bars · live")

    def _on_chart_bar_update(self, req_id: int, ticker: str, bar: dict):
        if req_id != self._req_id:
            return
        if self._page_loaded:
            self._push_update(bar)
        else:
            self._pending_updates.append(bar)

    def _on_chart_error(self, ticker: str, error_msg: str):
        if ticker != self._ticker:
            return
        if self._req_id is None or self._pending_bars is not None:
            self.status_label.setText(f"Error: {error_msg}")

    # -- JS bridge ---------------------------------------------------------

    def _push_bars(self, bars: list):
        payload = [self._bar_to_lwc(b) for b in bars if self._bar_to_lwc(b)]
        payload.sort(key=lambda b: b['time'])
        deduped = []
        last_t = None
        for b in payload:
            if b['time'] == last_t:
                deduped[-1] = b
            else:
                deduped.append(b)
            last_t = b['time']
        js = f"window.setBars({json.dumps(json.dumps(deduped))});"
        self.web_view.page().runJavaScript(js)

    def _push_update(self, bar: dict):
        lwc = self._bar_to_lwc(bar)
        if not lwc:
            return
        js = f"window.updateBar({json.dumps(json.dumps(lwc))});"
        self.web_view.page().runJavaScript(js)

    @staticmethod
    def _bar_to_lwc(bar: dict) -> Optional[dict]:
        try:
            t = int(bar['date'])
        except (TypeError, ValueError, KeyError):
            return None
        return {
            'time': t,
            'open': float(bar['open']),
            'high': float(bar['high']),
            'low': float(bar['low']),
            'close': float(bar['close']),
        }
