
// ============================================================
// 🤖 AI PRO MAX - FAST & SIMPLE SCANNER
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
const REQUEST_TIMEOUT = 10000;
const MAX_CONCURRENT_REQUESTS = 10;

// ============================================================
// 🌐 EXPRESS
// ============================================================

const app = express();
app.use(express.json());

app.get("/", (req, res) => res.status(200).send("AI PRO MAX is running"));
app.get("/health", (req, res) => res.status(200).json({ status: "online", time: new Date().toISOString() }));

app.listen(PORT, "0.0.0.0", () => {
    console.log(`AI PRO MAX server running on port ${PORT}`);
});

// ============================================================
// 🤖 TELEGRAM BOTS & CHATS
// ============================================================

const usBot = US_TOKEN ? new TelegramBot(US_TOKEN, { polling: true }) : null;
const tasiBot = TASI_TOKEN ? new TelegramBot(TASI_TOKEN, { polling: true }) : null;
const cryptoBot = CRYPTO_TOKEN ? new TelegramBot(CRYPTO_TOKEN, { polling: true }) : null;

const usChatIds = new Set();
const tasiChatIds = new Set();
const cryptoChatIds = new Set();

// ============================================================
// 📦 SYMBOLS
// ============================================================

let US_SYMBOLS = [];
let TASI_SYMBOLS = [];
let CRYPTO_SYMBOLS = [];
let SAUDI_EXCHANGE = null;
let marketsLoaded = false;

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
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return text ? JSON.parse(text) : null;
    } finally {
        clearTimeout(timer);
    }
}

// ============================================================
// 📋 LOAD MARKETS
// ============================================================

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
        const exchanges = await eodhd("exchanges-list/");
        const found = exchanges.find(e => String(e.CountryISO2 || "").toUpperCase() === "SA" || String(e.Name || "").toLowerCase().includes("tadawul"));
        SAUDI_EXCHANGE = found ? found.Code : "SR";
        TASI_SYMBOLS = await loadExchangeSymbols(SAUDI_EXCHANGE, "common_stock");
    } catch (e) { TASI_SYMBOLS = []; }

    try {
        CRYPTO_SYMBOLS = await loadExchangeSymbols("CC");
    } catch (e) { CRYPTO_SYMBOLS = []; }

    marketsLoaded = true;
    console.log(`Loaded -> US: ${US_SYMBOLS.length}, TASI: ${TASI_SYMBOLS.length}, CRYPTO: ${CRYPTO_SYMBOLS.length}`);
}

// ============================================================
// 📊 SIMPLE & ACCURATE ANALYSIS
// ============================================================

async function getDailyData(symbol) {
    const dateAgo = new Date();
    dateAgo.setDate(dateAgo.getDate() - 60);
    const data = await eodhd(`eod/${encodeURIComponent(symbol)}`, { period: "d", order: "d", from: dateAgo.toISOString().slice(0, 10) });
    if (!Array.isArray(data) || data.length < 15) return [];
    return data.reverse().map(r => Number(r.close)).filter(Number.isFinite);
}

function calculateEMA(values, period) {
    if (values.length < period) return null;
    const k = 2 / (period + 1);
    let ema = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
    for (let i = period; i < values.length; i++) {
        ema = (values[i] - ema) * k + ema;
    }
    return ema;
}

function analyze(closes) {
    if (closes.length < 15) return null;
    const price = closes.at(-1);
    const ema7 = calculateEMA(closes, 7);
    const ema21 = calculateEMA(closes, 21);

    if (!ema7 || !ema21) return null;

    let direction = "محايد";
    if (price > ema7 && ema7 > ema21) direction = "صعود";
    else if (price < ema7 && ema7 < ema21) direction = "هبوط";

    return { price, direction };
}

// ============================================================
// 📣 BROADCAST
// ============================================================

async function broadcast(bot, chatIds, message) {
    if (!bot || chatIds.size === 0) return;
    for (const chatId of chatIds) {
        try {
            await bot.sendMessage(chatId, message, { parse_mode: "HTML", disable_web_page_preview: true });
        } catch (e) {}
    }
}

// ============================================================
// 🔍 SCANNER ROUTINE (فحص سريع ومباشر)
// ============================================================

async function scanMarketRoutine(symbols, marketName, bot, chatIds) {
    if (!symbols.length || chatIds.size ===.0 || chatIds.size === 0) return;
    let count = 0;

    // نفحص أول 25 سهم كمثال للسرعة الفورية وتأكيد وصول الرسائل
    for (const item of symbols.slice(0, 25)) {
        try {
            const closes = await getDailyData(item.symbol);
            const res = analyze(closes);
            if (!res || res.direction === "محايد") continue;

            const msg = `<b>📊 AI PRO MAX - ${marketName}</b>\n\n` +
                        `<b>الرمز:</b> ${item.symbol}\n` +
                        `<b>الاسم:</b> ${item.name}\n` +
                        `<b>الحالة:</b> ${res.direction === "صعود" ? "🟢 صعود قوي" : "🔴 هبوط قوي"}\n` +
                        `<b>السعر الحالي:</b> ${res.price.toFixed(2)}`;

            await broadcast(bot, chatIds, msg);
            count++;
            if (count >= 3) break; // يرسل أول 3 إشارات واضحة فوراً لتتأكد أن كل شيء يعمل
        } catch (e) {}
    }
}

// ============================================================
// 🤖 BOT COMMANDS
// ============================================================

function setupBot(bot, chatIds, name, symbols) {
    if (!bot) return;
    bot.onText(/\/start|\/scan/, async (msg) => {
        const chatId = msg.chat.id;
        chatIds.add(chatId);
        await bot.sendMessage(chatId, `✅ تم ربط بوت ${name} بنجاح!\nجاري الفحص المباشر وإرسال النتائج...`, { parse_mode: "HTML" });
        scanMarketRoutine(symbols, name, bot, chatIds);
    });
}

setupBot(usBot, usChatIds, "السوق الأمريكي", US_SYMBOLS);
setupBot(tasiBot, tasiChatIds, "السوق السعودي", TASI_SYMBOLS);
setupBot(cryptoBot, cryptoChatIds, "العملات الرقمية", CRYPTO_SYMBOLS);

// ============================================================
// 🚀 START
// ============================================================

async function start() {
    await loadMarkets();
    setInterval(() => {
        if (marketsLoaded) {
            scanMarketRoutine(US_SYMBOLS, "السوق الأمريكي", usBot, usChatIds);
            scanMarketRoutine(TASI_SYMBOLS, "السوق السعودي", tasiBot, tasiChatIds);
            scanMarketRoutine(CRYPTO_SYMBOLS, "العملات الرقمية", cryptoBot, cryptoChatIds);
        }
    }, SCAN_INTERVAL);
}

start();
