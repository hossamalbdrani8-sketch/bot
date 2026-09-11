
// ============================================================
// 🤖 AI PRO MAX
// 🇺🇸 أمريكي + 🇸🇦 سعودي + 🪙 عملات رقمية
// EODHD + Telegram + Railway
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ CONFIGURATION
// ============================================================

const EODHD_API_KEY = process.env.EODHD_API_KEY;

const US_TOKEN = process.env.US_TOKEN;
const US_CHAT_ID = process.env.US_CHAT_ID;

const TASI_TOKEN = process.env.TASI_TOKEN;
const TASI_CHAT_ID = process.env.TASI_CHAT_ID;

const CRYPTO_TOKEN = process.env.CRYPTO_TOKEN;
const CRYPTO_CHAT_ID = process.env.CRYPTO_CHAT_ID;

const PORT = Number(process.env.PORT || 3000);

// ============================================================
// ⚙️ SCANNER SETTINGS
// ============================================================

const SCAN_INTERVAL = 60 * 1000;

const US_MIN_PRICE = 0.20;

const REQUEST_TIMEOUT = 15000;

const MAX_CONCURRENT_REQUESTS = 8;

const SIGNAL_COOLDOWN = 10 * 60 * 1000;

const NEWS_COOLDOWN = 30 * 60 * 1000;

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
// 🤖 TELEGRAM BOTS
// ============================================================

const usBot = US_TOKEN
    ? new TelegramBot(US_TOKEN, { polling: true })
    : null;

const tasiBot = TASI_TOKEN
    ? new TelegramBot(TASI_TOKEN, { polling: true })
    : null;

const cryptoBot = CRYPTO_TOKEN
    ? new TelegramBot(CRYPTO_TOKEN, { polling: true })
    : null;

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
const lastNews = new Map();

// ============================================================
// 🌐 EODHD REQUEST
// ============================================================

async function eodhd(path, params = {}) {

    if (!EODHD_API_KEY) {
        throw new Error("EODHD API key is not configured");
    }

    const url = new URL(`https://eodhd.com/api/${path}`);

    url.searchParams.set("api_token", EODHD_API_KEY);
    url.searchParams.set("fmt", "json");

    for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null) {
            url.searchParams.set(key, value);
        }
    }

    const controller = new AbortController();

    const timer = setTimeout(() => {
        controller.abort();
    }, REQUEST_TIMEOUT);

    try {

        const response = await fetch(url, {
            method: "GET",
            signal: controller.signal
        });

        const text = await response.text();

        if (!response.ok) {
            throw new Error(
                `EODHD HTTP ${response.status}: ${text.slice(0, 300)}`
            );
        }

        if (!text) {
            return null;
        }

        return JSON.parse(text);

    } finally {
        clearTimeout(timer);
    }
}

// ============================================================
// 🔎 DISCOVER SAUDI EXCHANGE
// ============================================================

async function discoverSaudiExchange() {

    const exchanges = await eodhd("exchanges-list/");

    if (!Array.isArray(exchanges)) {
        throw new Error("Invalid exchanges response");
    }

    const candidates = exchanges.filter(exchange => {

        const country =
            String(exchange.Country || "").toLowerCase();

        const iso =
            String(exchange.CountryISO2 || "").toUpperCase();

        const name =
            String(exchange.Name || "").toLowerCase();

        return (
            iso === "SA" ||
            country.includes("saudi") ||
            name.includes("tadawul") ||
            name.includes("saudi")
        );
    });

    const preferred = candidates.find(exchange => {

        const name =
            String(exchange.Name || "").toLowerCase();

        return (
            name.includes("tadawul") ||
            name.includes("saudi stock")
        );
    });

    const result = preferred || candidates[0];

    if (!result || !result.Code) {
        throw new Error("Saudi exchange was not found");
    }

    SAUDI_EXCHANGE = result.Code;

    console.log(
        `Saudi exchange detected: ${SAUDI_EXCHANGE} - ${result.Name}`
    );

    return SAUDI_EXCHANGE;
}

// ============================================================
// 📋 LOAD EXCHANGE SYMBOLS
// ============================================================

async function loadExchangeSymbols(exchange, type = null) {

    const params = {};

    if (type) {
        params.type = type;
    }

    const data = await eodhd(
        `exchange-symbol-list/${encodeURIComponent(exchange)}`,
        params
    );

    if (!Array.isArray(data)) {
        throw new Error(
            `Invalid symbols response for ${exchange}`
        );
    }

    return data
        .filter(item => item && item.Code)
        .map(item => ({
            code: String(item.Code).trim(),
            name: String(item.Name || item.Code).trim(),
            type: String(item.Type || "").trim(),
            exchange: String(item.Exchange || exchange).trim(),
            currency: String(item.Currency || "").trim()
        }));
}

// ============================================================
// 🇺🇸 LOAD US MARKET
// ============================================================

async function loadUSMarket() {

    console.log("Loading US symbols...");

    const symbols = await loadExchangeSymbols(
        "US",
        "common_stock"
    );

    US_SYMBOLS = symbols
        .map(item => ({
            ...item,
            symbol: `${item.code}.US`
        }));

    console.log(
        `US symbols loaded: ${US_SYMBOLS.length}`
    );
}

// ============================================================
// 🇸🇦 LOAD TASI
// ============================================================

async function loadTASI() {

    if (!SAUDI_EXCHANGE) {
        await discoverSaudiExchange();
    }

    console.log(
        `Loading Saudi symbols from ${SAUDI_EXCHANGE}...`
    );

    const symbols = await loadExchangeSymbols(
        SAUDI_EXCHANGE,
        "common_stock"
    );

    TASI_SYMBOLS = symbols
        .map(item => ({
            ...item,
            symbol: `${item.code}.${SAUDI_EXCHANGE}`
        }));

    console.log(
        `Saudi symbols loaded: ${TASI_SYMBOLS.length}`
    );
}

// ============================================================
// 🪙 LOAD CRYPTO
// ============================================================

async function loadCrypto() {

    console.log("Loading crypto symbols...");

    const symbols = await loadExchangeSymbols("CC");

    CRYPTO_SYMBOLS = symbols
        .map(item => ({
            ...item,
            symbol: `${item.code}.CC`
        }));

    console.log(
        `Crypto symbols loaded: ${CRYPTO_SYMBOLS.length}`
    );
}

// ============================================================
// 🔄 LOAD ALL MARKETS
// ============================================================

async function loadMarkets() {

    try {

        await loadUSMarket();

    } catch (error) {

        console.log(
            `US market loading problem: ${error.message}`
        );

        US_SYMBOLS = [];
    }

    try {

        await loadTASI();

    } catch (error) {

        console.log(
            `Saudi market loading problem: ${error.message}`
        );

        TASI_SYMBOLS = [];
    }

    try {

        await loadCrypto();

    } catch (error) {

        console.log(
            `Crypto loading problem: ${error.message}`
        );

        CRYPTO_SYMBOLS = [];
    }

    marketsLoaded = true;

    console.log("");
    console.log("AI PRO MAX markets ready");
    console.log(`US: ${US_SYMBOLS.length}`);
    console.log(`TASI: ${TASI_SYMBOLS.length}`);
    console.log(`CRYPTO: ${CRYPTO_SYMBOLS.length}`);
}

// ============================================================
// 📊 GET DAILY DATA
// ============================================================

async function getDailyData(symbol) {

    const data = await eodhd(
        `eod/${encodeURIComponent(symbol)}`,
        {
            period: "d",
            order: "d",
            from: getDateDaysAgo(180)
        }
    );

    if (!Array.isArray(data) || data.length < 20) {
        return [];
    }

    return data
        .reverse()
        .filter(row =>
            row &&
            Number.isFinite(Number(row.close))
        );
}

// ============================================================
// 📈 EMA
// ============================================================

function calculateEMA(values, period) {

    if (!Array.isArray(values) || values.length < period) {
        return null;
    }

    const multiplier = 2 / (period + 1);

    let ema = values
        .slice(0, period)
        .reduce((a, b) => a + b, 0) / period;

    for (let i = period; i < values.length; i++) {
        ema =
            (values[i] - ema) * multiplier +
            ema;
    }

    return ema;
}

// ============================================================
// 📐 ATR
// ============================================================

function calculateATR(rows, period = 14) {

    if (!rows || rows.length < period + 1) {
        return null;
    }

    const trs = [];

    for (let i = 1; i < rows.length; i++) {

        const high = Number(rows[i].high);
        const low = Number(rows[i].low);
        const previousClose = Number(rows[i - 1].close);

        if (
            !Number.isFinite(high) ||
            !Number.isFinite(low) ||
            !Number.isFinite(previousClose)
        ) {
            continue;
        }

        const tr = Math.max(
            high - low,
            Math.abs(high - previousClose),
            Math.abs(low - previousClose)
        );

        trs.push(tr);
    }

    if (trs.length < period) {
        return null;
    }

    return trs
        .slice(-period)
        .reduce((a, b) => a + b, 0) / period;
}

// ============================================================
// 📊 SUPPORT / RESISTANCE
// ============================================================

function calculateSupportResistance(rows) {

    const recent = rows.slice(-20);

    const highs = recent
        .map(x => Number(x.high))
        .filter(Number.isFinite);

    const lows = recent
        .map(x => Number(x.low))
        .filter(Number.isFinite);

    if (!highs.length || !lows.length) {
        return {
            support: null,
            resistance: null
        };
    }

    return {
        support: Math.min(...lows),
        resistance: Math.max(...highs)
    };
}

// ============================================================
// 📊 VOLUME STRENGTH
// ============================================================

function calculateVolumeStrength(rows) {

    const volumes = rows
        .slice(-21, -1)
        .map(x => Number(x.volume))
        .filter(Number.isFinite);

    const latest =
        Number(rows.at(-1)?.volume);

    if (!volumes.length || !Number.isFinite(latest)) {
        return null;
    }

    const average =
        volumes.reduce((a, b) => a + b, 0) /
        volumes.length;

    if (!average) {
        return null;
    }

    return latest / average;
}

// ============================================================
// 🧠 ANALYZE SYMBOL
// ============================================================

function analyzeSymbol(rows) {

    if (!rows || rows.length < 20) {
        return null;
    }

    const closes = rows
        .map(row => Number(row.close))
        .filter(Number.isFinite);

    const price = closes.at(-1);

    if (!Number.isFinite(price) || price <= 0) {
        return null;
    }

    const ema7 = calculateEMA(closes, 7);
    const ema14 = calculateEMA(closes, 14);
    const ema25 = calculateEMA(closes, 25);
    const ema50 = calculateEMA(closes, 50);

    const atr = calculateATR(rows, 14);

    const sr =
        calculateSupportResistance(rows);

    const volumeStrength =
        calculateVolumeStrength(rows);

    let direction = "محايد";

    if (
        ema7 !== null &&
        ema14 !== null &&
        ema25 !== null
    ) {

        if (
            price > ema7 &&
            ema7 > ema14 &&
            ema14 > ema25
        ) {
            direction = "صعود";
        }

        if (
            price < ema7 &&
            ema7 < ema14 &&
            ema14 < ema25
        ) {
            direction = "هبوط";
        }
    }

    let strength = 60;

    if (direction === "صعود") {

        strength += 10;

        if (
            volumeStrength !== null &&
            volumeStrength >= 1.5
        ) {
            strength += 10;
        }

        if (
            ema50 !== null &&
            price > ema50
        ) {
            strength += 10;
        }
    }

    if (direction === "هبوط") {

        strength += 10;

        if (
            volumeStrength !== null &&
            volumeStrength >= 1.5
        ) {
            strength += 10;
        }

        if (
            ema50 !== null &&
            price < ema50
        ) {
            strength += 10;
        }
    }

    strength = Math.min(100, strength);

    return {
        price,
        ema7,
        ema14,
        ema25,
        ema50,
        atr,
        support: sr.support,
        resistance: sr.resistance,
        volumeStrength,
        direction,
        strength
    };
}

// ============================================================
// 🎯 ATR TARGETS
// ============================================================

function calculateTargets(price, atr, direction) {

    if (!Number.isFinite(price)) {
        return [];
    }

    const safeATR =
        Number.isFinite(atr) && atr > 0
            ? atr
            : price * 0.02;

    const multipliers = [
        0.5,
        1,
        1.5,
        2,
        2.5,
        3,
        3.5,
        4
    ];

    return multipliers.map((multiplier, index) => {

        const distance =
            safeATR * multiplier;

        const target =
            direction === "هبوط"
                ? price - distance
                : price + distance;

        return {
            name: `TP${index + 1}`,
            price: target
        };
    });
}

// ============================================================
// 💰 FORMAT PRICE
// ============================================================

function formatPrice(value) {

    if (!Number.isFinite(Number(value))) {
        return "-";
    }

    const number = Number(value);

    if (number < 1) {
        return number.toFixed(4);
    }

    if (number < 10) {
        return number.toFixed(3);
    }

    return number.toFixed(2);
}

// ============================================================
// 📊 FORMAT PERCENT
// ============================================================

function formatPercent(value) {

    if (!Number.isFinite(Number(value))) {
        return "-";
    }

    return `${Number(value).toFixed(2)}%`;
}

// ============================================================
// 📩 TELEGRAM SEND
// ============================================================

async function sendTelegram(bot, chatId, message) {

    if (!bot || !chatId) {
        return;
    }

    try {

        await bot.sendMessage(
            chatId,
            message,
            {
                parse_mode: "HTML",
                disable_web_page_preview: true
            }
        );

    } catch (error) {

        console.log(
            `Telegram send problem: ${error.message}`
        );
    }
}

// ============================================================
// 🔐 SIGNAL COOLDOWN
// ============================================================

function canSendSignal(symbol, direction) {

    const key = `${symbol}:${direction}`;

    const previous =
        lastSignals.get(key);

    const now = Date.now();

    if (
        previous &&
        now - previous < SIGNAL_COOLDOWN
    ) {
        return false;
    }

    lastSignals.set(key, now);

    return true;
}

// ============================================================
// 📰 US NEWS
// ============================================================

async function getUSNews(symbol) {

    try {

        const news = await eodhd(
            "news",
            {
                s: symbol,
                limit: 10
            }
        );

        if (!Array.isArray(news)) {
            return [];
        }

        return news
            .map(article => {

                const sentiment =
                    article.sentiment || {};

                const polarity =
                    Number(sentiment.polarity || 0);

                const pos =
                    Number(sentiment.pos || 0);

                const neg =
                    Number(sentiment.neg || 0);

                let type = null;

                if (
                    polarity > 0 ||
                    pos > neg
                ) {
                    type = "إيجابي";
                }

                if (
                    polarity < 0 ||
                    neg > pos
                ) {
                    type = "سلبي";
                }

                if (!type) {
                    return null;
                }

                return {
                    type,
                    title:
                        article.title ||
                        "خبر جديد",
                    link:
                        article.link ||
                        "",
                    date:
                        article.date ||
                        ""
                };

            })
            .filter(Boolean);

    } catch (error) {

        console.log(
            `News problem ${symbol}: ${error.message}`
        );

        return [];
    }
}

// ============================================================
// 📰 SEND STOCK NEWS
// ============================================================

async function sendStockNews(symbol, companyName) {

    const news =
        await getUSNews(symbol);

    for (const article of news) {

        const key =
            `${symbol}:${article.title}`;

        const previous =
            lastNews.get(key);

        if (previous) {
            continue;
        }

        lastNews.set(key, Date.now());

        const emoji =
            article.type === "إيجابي"
                ? "🟢"
                : "🔴";

        const message = `
<b>🇺🇸 AI PRO MAX</b>

<b>${symbol}</b>
${companyName || ""}

<b>خبر ${article.type} ${emoji}</b>

${escapeHTML(article.title)}

${article.link || ""}
`;

        await sendTelegram(
            usBot,
            US_CHAT_ID,
            message
        );
    }
}

// ============================================================
// 🧹 ESCAPE HTML
// ============================================================

function escapeHTML(text) {

    return String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

// ============================================================
// 📣 BUILD SIGNAL
// ============================================================

function buildSignalMessage(
    market,
    item,
    analysis
) {

    const {
        price,
        atr,
        support,
        resistance,
        volumeStrength,
        direction,
        strength
    } = analysis;

    const targets =
        calculateTargets(
            price,
            atr,
            direction
        );

    const signalEmoji =
        direction === "صعود"
            ? "🟢"
            : "🔴";

    let message = `
<b>AI PRO MAX</b>

${market}

<b>${escapeHTML(item.symbol)}</b>
${escapeHTML(item.name)}

<b>الإشارة: ${signalEmoji} ${direction}</b>

<b>قوة الإشارة:</b> ${strength}%

<b>السعر:</b> ${formatPrice(price)}

<b>الدخول:</b> ${formatPrice(price)}

<b>الدعم:</b> ${formatPrice(support)}

<b>المقاومة:</b> ${formatPrice(resistance)}

<b>ATR:</b> ${formatPrice(atr)}

<b>قوة الفوليوم:</b> ${
    volumeStrength !== null
        ? volumeStrength.toFixed(2) + "x"
        : "-"
}
`;

    if (targets.length) {

        message += `\n<b>الأهداف</b>\n`;

        for (const target of targets) {

            message +=
                `${target.name}: ${formatPrice(target.price)}\n`;
        }
    }

    return message;
}

// ============================================================
// 🔍 ANALYZE ONE SYMBOL
// ============================================================

async function scanSymbol(
    item,
    market,
    bot,
    chatId
) {

    try {

        const rows =
            await getDailyData(item.symbol);

        if (!rows.length) {
            return;
        }

        const analysis =
            analyzeSymbol(rows);

        if (!analysis) {
            return;
        }

        if (
            market === "🇺🇸 السوق الأمريكي" &&
            analysis.price < US_MIN_PRICE
        ) {
            return;
        }

        if (
            analysis.direction === "محايد"
        ) {
            return;
        }

        if (
            !canSendSignal(
                item.symbol,
                analysis.direction
            )
        ) {
            return;
        }

        const message =
            buildSignalMessage(
                market,
                item,
                analysis
            );

        await sendTelegram(
            bot,
            chatId,
            message
        );

        if (
            market === "🇺🇸 السوق الأمريكي"
        ) {

            await sendStockNews(
                item.symbol,
                item.name
            );
        }

    } catch (error) {

        console.log(
            `Scan problem ${item.symbol}: ${error.message}`
        );
    }
}

// ============================================================
// 🚦 CONCURRENT SCANNER
// ============================================================

async function scanMarket(
    symbols,
    market,
    bot,
    chatId,
    stateName
) {

    if (!symbols.length) {
        console.log(`${market}: no symbols loaded`);
        return;
    }

    if (stateName.value) {
        console.log(`${market}: previous scan still running`);
        return;
    }

    stateName.value = true;

    console.log("");
    console.log(`Scanning ${market}`);
    console.log(`Symbols: ${symbols.length}`);

    try {

        let index = 0;

        async function worker() {

            while (true) {

                const current =
                    index++;

                if (current >= symbols.length) {
                    return;
                }

                await scanSymbol(
                    symbols[current],
                    market,
                    bot,
                    chatId
                );
            }
        }

        const workers = [];

        const count =
            Math.min(
                MAX_CONCURRENT_REQUESTS,
                symbols.length
            );

        for (let i = 0; i < count; i++) {
            workers.push(worker());
        }

        await Promise.all(workers);

    } catch (error) {

        console.log(
            `${market} scan problem: ${error.message}`
        );

    } finally {

        stateName.value = false;
    }
}

// ============================================================
// 🇺🇸 US SCAN
// ============================================================

async function scanUS() {

    await scanMarket(
        US_SYMBOLS,
        "🇺🇸 السوق الأمريكي",
        usBot,
        US_CHAT_ID,
        {
            get value() {
                return usScanning;
            },
            set value(value) {
                usScanning = value;
            }
        }
    );
}

// ============================================================
// 🇸🇦 TASI SCAN
// ============================================================

async function scanTASI() {

    await scanMarket(
        TASI_SYMBOLS,
        "🇸🇦 السوق السعودي",
        tasiBot,
        TASI_CHAT_ID,
        {
            get value() {
                return tasiScanning;
            },
            set value(value) {
                tasiScanning = value;
            }
        }
    );
}

// ============================================================
// 🪙 CRYPTO SCAN
// ============================================================

async function scanCrypto() {

    await scanMarket(
        CRYPTO_SYMBOLS,
        "🪙 العملات الرقمية",
        cryptoBot,
        CRYPTO_CHAT_ID,
        {
            get value() {
                return cryptoScanning;
            },
            set value(value) {
                cryptoScanning = value;
            }
        }
    );
}

// ============================================================
// ⏱️ AUTOMATIC SCAN
// ============================================================

async function runAllScans() {

    if (!marketsLoaded) {
        return;
    }

    console.log("");
    console.log("Starting AI PRO MAX scan cycle");

    await Promise.allSettled([
        scanUS(),
        scanTASI(),
        scanCrypto()
    ]);

    console.log("Scan cycle finished");
}

// ============================================================
// 🧹 CLEAN OLD MEMORY
// ============================================================

setInterval(() => {

    const now = Date.now();

    for (const [key, time] of lastSignals) {

        if (
            now - time >
            SIGNAL_COOLDOWN * 3
        ) {
            lastSignals.delete(key);
        }
    }

    for (const [key, time] of lastNews) {

        if (
            now - time >
            NEWS_COOLDOWN * 3
        ) {
            lastNews.delete(key);
        }
    }

}, 5 * 60 * 1000);

// ============================================================
// 🤖 BOT START COMMANDS
// ============================================================

if (usBot) {

    usBot.onText(/^\/start$/, async () => {

        await sendTelegram(
            usBot,
            US_CHAT_ID,
            `
<b>AI PRO MAX</b>

🇺🇸 تم تشغيل بوت السوق الأمريكي

الفحص تلقائي.

الحد الأدنى للسعر:
$${US_MIN_PRICE}

الإشارات:
🟢 صعود
🔴 هبوط

الأخبار:
🟢 إيجابي
🔴 سلبي
`
        );
    });

    usBot.on("polling_error", error => {

        console.log(
            `US Telegram polling: ${error.message}`
        );
    });
}

if (tasiBot) {

    tasiBot.onText(/^\/start$/, async () => {

        await sendTelegram(
            tasiBot,
            TASI_CHAT_ID,
            `
<b>AI PRO MAX</b>

🇸🇦 تم تشغيل بوت السوق السعودي

الفحص تلقائي.
`
        );
    });

    tasiBot.on("polling_error", error => {

        console.log(
            `TASI Telegram polling: ${error.message}`
        );
    });
}

if (cryptoBot) {

    cryptoBot.onText(/^\/start$/, async () => {

        await sendTelegram(
            cryptoBot,
            CRYPTO_CHAT_ID,
            `
<b>AI PRO MAX</b>

🪙 تم تشغيل بوت العملات الرقمية

الفحص تلقائي.
`
        );
    });

    cryptoBot.on("polling_error", error => {

        console.log(
            `Crypto Telegram polling: ${error.message}`
        );
    });
}

// ============================================================
// 📅 DATE
// ============================================================

function getDateDaysAgo(days) {

    const date = new Date();

    date.setDate(
        date.getDate() - days
    );

    return date
        .toISOString()
        .slice(0, 10);
}

// ============================================================
// 🚀 START
// ============================================================

async function start() {

    console.log("");
    console.log("============================================");
    console.log("AI PRO MAX");
    console.log("US + TASI + CRYPTO");
    console.log("============================================");

    await loadMarkets();

    console.log("");
    console.log("Automatic scanner started");

    setTimeout(() => {
        runAllScans();
    }, 5000);

    setInterval(() => {

        runAllScans();

    }, SCAN_INTERVAL);
}

// ============================================================
// 🛡️ GLOBAL ERROR HANDLING
// ============================================================

process.on("unhandledRejection", error => {

    console.log(
        `Unhandled rejection: ${
            error?.message || error
        }`
    );
});

process.on("uncaughtException", error => {

    console.log(
        `Uncaught exception: ${
            error?.message || error
        }`
    );
});

// ============================================================
// ▶️ RUN
// ============================================================

start().catch(error => {

    console.log(
        `Startup problem: ${
            error?.message || error
        }`
    );
});