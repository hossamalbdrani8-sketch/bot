
// ============================================================
// 🤖 AI PRO MAX - ALL IN ONE BOTS
// 🇺🇸 أمريكي + 🇸🇦 سعودي + 🪙 عملات رقمية
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ CONFIGURATION
// ============================================================

const EODHD_API_KEY = process.env.EODHD_API_KEY;

const US_TOKEN = process.env.US_TOKEN;
const TASI_TOKEN = process.env.TASI_TOKEN;
const CRYPTO_TOKEN = process.env.CRYPTO_TOKEN;

const PORT = Number(process.env.PORT || 3000);
const SCAN_INTERVAL = 60 * 1000;
const US_MIN_PRICE = 0.20;
const REQUEST_TIMEOUT = 15000;
const MAX_CONCURRENT_REQUESTS = 8;
const SIGNAL_COOLDOWN = 10 * 60 * 1000;

// ============================================================
// 🌐 EXPRESS
// ============================================================

const app = express();
app.use(express.json());

app.get("/", (req, res) => {
    res.status(200).send("AI PRO MAX is running");
});

app.get("/health", (req, res) => {
    res.status(200).json({
        status: "online",
        system: "AI PRO MAX",
        markets: ["US", "TASI", "CRYPTO"],
        time: new Date().toISOString()
    });
});

app.listen(PORT, "0.0.0.0", () => {
    console.log(`AI PRO MAX server running on port ${PORT}`);
});

// ============================================================
// 🤖 TELEGRAM BOTS & CHAT IDS SETS
// ============================================================

const usBot = US_TOKEN ? new TelegramBot(US_TOKEN, { polling: true }) : null;
const tasiBot = TASI_TOKEN ? new TelegramBot(TASI_TOKEN, { polling: true }) : null;
const cryptoBot = CRYPTO_TOKEN ? new TelegramBot(CRYPTO_TOKEN, { polling: true }) : null;

const usChatIds = new Set();
const tasiChatIds = new Set();
const cryptoChatIds = new Set();

// ============================================================
// 📦 RUNTIME DATA
// ============================================================

let US_SYMBOLS = [];
let TASI_SYMBOLS = [];
let CRYPTO_SYMBOLS = [];
let SAUDI_EXCHANGE = null;
let marketsLoaded = false;

let usScanning = false;
let tasiScanning = false;
let cryptoScanning = false;

const lastSignals = new Map();

// ============================================================
// 🌐 EODHD REQUEST
// ============================================================

async function eodhd(path, params = {}) {
    if (!EODHD_API_KEY) throw new Error("EODHD API key is not configured");
    const url = new URL(`https://eodhd.com/api/${path}`);
    url.searchParams.set("api_token", EODHD_API_KEY);
    url.searchParams.set("fmt", "json");

    for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null) url.searchParams.set(key, value);
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

    try {
        const response = await fetch(url, { method: "GET", signal: controller.signal });
        const text = await response.text();
        if (!response.ok) throw new Error(`EODHD HTTP ${response.status}: ${text.slice(0, 300)}`);
        return text ? JSON.parse(text) : null;
    } finally {
        clearTimeout(timer);
    }
}

// ============================================================
// 🔎 DISCOVER SAUDI EXCHANGE & LOAD MARKETS
// ============================================================

async function discoverSaudiExchange() {
    const exchanges = await eodhd("exchanges-list/");
    if (!Array.isArray(exchanges)) throw new Error("Invalid exchanges response");
    const found = exchanges.find(e => String(e.CountryISO2 || "").toUpperCase() === "SA" || String(e.Name || "").toLowerCase().includes("tadawul"));
    SAUDI_EXCHANGE = found ? found.Code : "SR";
    return SAUDI_EXCHANGE;
}

async function loadExchangeSymbols(exchange, type = null) {
    const params = type ? { type } : {};
    const data = await eodhd(`exchange-symbol-list/${encodeURIComponent(exchange)}`, params);
    if (!Array.isArray(data)) return [];
    return data.filter(item => item && item.Code).map(item => ({
        code: String(item.Code).trim(),
        name: String(item.Name || item.Code).trim(),
        symbol: `${String(item.Code).trim()}.${exchange}`
    }));
}

async function loadMarkets() {
    try {
        US_SYMBOLS = await loadExchangeSymbols("US", "common_stock");
    } catch (e) { US_SYMBOLS = []; }

    try {
        if (!SAUDI_EXCHANGE) await discoverSaudiExchange();
        TASI_SYMBOLS = await loadExchangeSymbols(SAUDI_EXCHANGE, "common_stock");
    } catch (e) { TASI_SYMBOLS = []; }

    try {
        CRYPTO_SYMBOLS = await loadExchangeSymbols("CC");
    } catch (e) { CRYPTO_SYMBOLS = []; }

    marketsLoaded = true;
    console.log(`Markets loaded -> US: ${US_SYMBOLS.length}, TASI: ${TASI_SYMBOLS.length}, CRYPTO: ${CRYPTO_SYMBOLS.length}`);
}

// ============================================================
// 📊 ANALYSIS & UTILS
// ============================================================

async function getDailyData(symbol) {
    const dateAgo = new Date();
    dateAgo.setDate(dateAgo.getDate() - 180);
    const fromStr = dateAgo.toISOString().slice(0, 10);

    const data = await eodhd(`eod/${encodeURIComponent(symbol)}`, { period: "d", order: "d", from: fromStr });
    if (!Array.isArray(data) || data.length < 20) return [];
    return data.reverse().filter(row => row && Number.isFinite(Number(row.close)));
}

function calculateEMA(values, period) {
    if (!Array.isArray(values) || values.length < period) return null;
    const multiplier = 2 / (period + 1);
    let ema = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
    for (let i = period; i < values.length; i++) {
        ema = (values[i] - ema) * multiplier + ema;
    }
    return ema;
}

function calculateATR(rows, period = 14) {
    if (!rows || rows.length < period + 1) return null;
    const trs = [];
    for (let i = 1; i < rows.length; i++) {
        const high = Number(rows[i].high), low = Number(rows[i].low), prevClose = Number(rows[i - 1].close);
        if (!Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(prevClose)) continue;
        trs.push(Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose)));
    }
    if (trs.length < period) return null;
    return trs.slice(-period).reduce((a, b) => a + b, 0) / period;
}

function analyzeSymbol(rows) {
    if (!rows || rows.length < 20) return null;
    const closes = rows.map(r => Number(r.close)).filter(Number.isFinite);
    const price = closes.at(-1);
    if (!price) return null;

    const ema7 = calculateEMA(closes, 7);
    const ema14 = calculateEMA(closes, 14);
    const ema25 = calculateEMA(closes, 25);
    const atr = calculateATR(rows, 14);

    let direction = "محايد";
    if (ema7 && ema14 && ema25) {
        if (price > ema7 && ema7 > ema14 && ema14 > ema25) direction = "صعود";
        else if (price < ema7 && ema7 < ema14 && ema14 < ema25) direction = "هبوط";
    }

    const recent = rows.slice(-20);
    const support = Math.min(...recent.map(x => Number(x.low)).filter(Number.isFinite));
    const resistance = Math.max(...recent.map(x => Number(x.high)).filter(Number.isFinite));

    return { price, atr, support, resistance, direction, strength: direction !== "محايد" ? 80 : 50 };
}

function calculateTargets(price, atr, direction) {
    const safeATR = Number.isFinite(atr) && atr > 0 ? atr : price * 0.02;
    return [0.5, 1, 1.5, 2, 2.5, 3].map((m, i) => ({
        name: `TP${i + 1}`,
        price: direction === "هبوط" ? price - (safeATR * m) : price + (safeATR * m)
    }));
}

function formatPrice(v) { return Number.isFinite(Number(v)) ? Number(v).toFixed(2) : "-"; }
function escapeHTML(t) { return String(t || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

async function broadcast(bot, chatIds, message) {
    if (!bot || chatIds.size === 0) return;
    for (const chatId of chatIds) {
        try {
            await bot.sendMessage(chatId, message, { parse_mode: "HTML", disable_web_page_preview: true });
        } catch (e) {}
    }
}

// ============================================================
// 🔍 SCANNERS
// ============================================================

async function scanMarketRoutine(symbols, marketName, bot, chatIds) {
    if (!symbols.length || chatIds.size === 0) return;
    let sentCount = 0;

    for (const item of symbols) {
        if (sentCount >= 10) break; // إرسال أول 10 إشارات نشطة لتجنب الضغط
        try {
            const rows = await getDailyData(item.symbol);
            const analysis = analyzeSymbol(rows);
            if (!analysis || analysis.direction === "محايد") continue;
            if (marketName.includes("الأمريكي") && analysis.price < US_MIN_PRICE) continue;

            const targets = calculateTargets(analysis.price, analysis.atr, analysis.direction);
            let msg = `<b>AI PRO MAX - ${marketName}</b>\n\n`;
            msg += `<b>${escapeHTML(item.symbol)}</b> | ${escapeHTML(item.name)}\n`;
            msg += `الإشارة: <b>${analysis.direction === "صعود" ? "🟢 صعود" : "🔴 هبوط"}</b>\n`;
            msg += `السعر: <b>${formatPrice(analysis.price)}</b>\n`;
            msg += `الدعم: ${formatPrice(analysis.support)} | المقاومة: ${formatPrice(analysis.resistance)}\n\n<b>الأهداف:</b>\n`;
            targets.forEach(t => { msg += `${t.name}: ${formatPrice(t.price)}\n`; });

            await broadcast(bot, chatIds, msg);
            sentCount++;
        } catch (e) {}
    }
}

async function runAllScans() {
    if (!marketsLoaded) return;
    await Promise.allSettled([
        scanMarketRoutine(US_SYMBOLS, "السوق الأمريكي", usBot, usChatIds),
        scanMarketRoutine(TASI_SYMBOLS, "السوق السعودي", tasiBot, tasiChatIds),
        scanMarketRoutine(CRYPTO_SYMBOLS, "العملات الرقمية", cryptoBot, cryptoChatIds)
    ]);
}

// ============================================================
// 🤖 TELEGRAM HANDLERS (تسجيل الشات تلقائياً)
// ============================================================

function setupBotCommands(bot, chatIds, marketName) {
    if (!bot) return;
    bot.onText(/\/start|\/scan/, async (msg) => {
        const chatId = msg.chat.id;
        chatIds.add(chatId);
        await bot.sendMessage(chatId, `✅ تم تفعيل بوت ${marketName} بنجاح وتسجيل محادثتك!\nجاري فحص السوق وإرسال النتائج...`, { parse_mode: "HTML" });
        
        // فحص فوري عند طلب المستخدم
        if (marketName.includes("الأمريكي")) scanMarketRoutine(US_SYMBOLS, marketName, usBot, chatIds);
        if (marketName.includes("السعودي")) scanMarketRoutine(TASI_SYMBOLS, marketName, tasiBot, chatIds);
        if (marketName.includes("العملات")) scanMarketRoutine(CRYPTO_SYMBOLS, marketName, cryptoBot, chatIds);
    });
}

setupBotCommands(usBot, usChatIds, "السوق الأمريكي");
setupBotCommands(tasiBot, tasiChatIds, "السوق السعودي");
setupBotCommands(cryptoBot, cryptoChatIds, "العملات الرقمية");

// ============================================================
// 🚀 STARTUP
// ============================================================

async function start() {
    await loadMarkets();
    setInterval(runAllScans, SCAN_INTERVAL);
}

start();
