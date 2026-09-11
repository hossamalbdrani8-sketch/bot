
"use strict";

// ============================================================
// 💀🚀 AI PRO MAX
// BUILD FROM ZERO
// TASI + US + CRYPTO
// Telegram + Railway + EODHD
// ============================================================

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ CONFIGURATION
// ============================================================

const TASI_TOKEN = process.env.TASI_CONFIG;
const US_TOKEN = process.env.US_CONFIG;
const CRYPTO_TOKEN = process.env.CRYPTO_CONFIG;
const EODHD_API_KEY = process.env.EODHD_API_KEY;

const PORT = process.env.PORT || 8080;

const SCAN_EVERY = 2 * 60 * 1000;

// ============================================================
// 🤖 TELEGRAM
// ============================================================

const tasiBot = TASI_TOKEN
    ? new TelegramBot(TASI_TOKEN, { polling: false })
    : null;

const usBot = US_TOKEN
    ? new TelegramBot(US_TOKEN, { polling: false })
    : null;

const cryptoBot = CRYPTO_TOKEN
    ? new TelegramBot(CRYPTO_TOKEN, { polling: false })
    : null;

// ============================================================
// 🌐 SERVER
// ============================================================

const app = express();

app.use(express.json());

app.get("/", (req, res) => {
    res.status(200).send("💀🚀 AI PRO MAX ONLINE");
});

app.get("/health", (req, res) => {
    res.json({
        status: "online",
        bot: "AI PRO MAX",
        uptime: Math.floor(process.uptime()),
        time: new Date().toISOString()
    });
});

// ============================================================
// 📱 TELEGRAM WEBHOOK ROUTES
// ============================================================

app.post("/telegram/tasi", (req, res) => {

    if (tasiBot) {
        tasiBot.processUpdate(req.body);
    }

    res.sendStatus(200);
});

app.post("/telegram/us", (req, res) => {

    if (usBot) {
        usBot.processUpdate(req.body);
    }

    res.sendStatus(200);
});

app.post("/telegram/crypto", (req, res) => {

    if (cryptoBot) {
        cryptoBot.processUpdate(req.body);
    }

    res.sendStatus(200);
});

// ============================================================
// 💾 CHAT IDS
// ============================================================

const chats = {
    tasi: new Set(),
    us: new Set(),
    crypto: new Set()
};

// ============================================================
// 📨 START MESSAGE
// ============================================================

function startMessage(market) {

    let marketText;

    if (market === "tasi") {
        marketText = "السوق السعودي TASI 🇸🇦";
    }

    if (market === "us") {
        marketText = "السوق الأمريكي 🇺🇸";
    }

    if (market === "crypto") {
        marketText = "العملات الرقمية 🪙";
    }

    return `💀🚀 AI PRO MAX

✅ البوت يعمل الآن
🔄 الفحص تلقائي وكامل
⏱️ الفحص كل دقيقتين

📊 السوق:
${marketText}

🧠 المحرك الذكي:

• EMA 8
• EMA 21
• EMA 50
• RSI 14
• ATR 14
• دعم
• مقاومة
• قوة الحجم
• قوة الشراء
• قوة البيع
• 8 أهداف ATR
• منع تكرار التنبيهات

🟢⬆️ سهم أخضر = صعود قوي
🔴⬇️ سهم أحمر = هبوط قوي

🤖 لا تحتاج إلى تشغيل الفحص يدويًا.

📡 مصدر البيانات:
EODHD فقط`;
}

// ============================================================
// ▶️ START COMMAND
// ============================================================

function setupStart(bot, market) {

    if (!bot) return;

    bot.onText(/^\/start$/i, async (msg) => {

        chats[market].add(msg.chat.id);

        try {
            await bot.sendMessage(
                msg.chat.id,
                startMessage(market)
            );
        } catch (err) {
            console.log(
                "Telegram:",
                err.message
            );
        }
    });
}

setupStart(tasiBot, "tasi");
setupStart(usBot, "us");
setupStart(cryptoBot, "crypto");

// ============================================================
// 📡 WEBHOOK SETUP
// ============================================================

async function setupWebhook(bot, market) {

    if (!bot) return;

    const domain =
        process.env.RAILWAY_PUBLIC_DOMAIN ||
        process.env.RAILWAY_STATIC_URL;

    if (!domain) {
        console.log(
            `Telegram Webhook ${market}: waiting for Railway domain`
        );
        return;
    }

    const clean =
        domain
            .replace(/^https?:\/\//, "")
            .replace(/\/+$/, "");

    const webhookURL =
        `https://${clean}/telegram/${market}`;

    try {

        await bot.setWebHook(webhookURL);

        console.log(
            `Telegram Webhook: ${market} ON`
        );

    } catch (err) {

        console.log(
            `Telegram Webhook ${market}:`,
            err.message
        );
    }
}

// ============================================================
// 📡 EODHD
// ============================================================

async function eodhd(path, params = {}) {

    const url =
        new URL(
            `https://eodhd.com/api/${path}`
        );

    url.searchParams.set(
        "api_token",
        EODHD_API_KEY
    );

    url.searchParams.set(
        "fmt",
        "json"
    );

    for (
        const [key, value]
        of Object.entries(params)
    ) {

        url.searchParams.set(
            key,
            value
        );
    }

    const response =
        await fetch(url);

    const text =
        await response.text();

    let data;

    try {
        data = JSON.parse(text);
    } catch {
        data = text;
    }

    if (!response.ok) {

        throw new Error(
            `EODHD HTTP ${response.status}`
        );
    }

    return data;
}

// ============================================================
// 📚 SYMBOL LIST
// ============================================================

const symbolCache = {
    us: [],
    crypto: []
};

const symbolCacheTime = {
    us: 0,
    crypto: 0
};

// ============================================================
// 🇺🇸 US
// ============================================================

async function getUSSymbols() {

    const now = Date.now();

    if (
        symbolCache.us.length > 0 &&
        now - symbolCacheTime.us < 60 * 60 * 1000
    ) {
        return symbolCache.us;
    }

    try {

        console.log(
            "US: تحميل قائمة الأسهم"
        );

        const data =
            await eodhd(
                "exchange-symbol-list/US"
            );

        if (!Array.isArray(data)) {
            return [];
        }

        const symbols =
            data
                .filter(x => x && x.Code)
                .filter(x => {

                    const exchange =
                        String(
                            x.Exchange || ""
                        ).toUpperCase();

                    return (
                        exchange === "NASDAQ" ||
                        exchange === "NYSE" ||
                        exchange === "AMEX"
                    );
                })
                .map(x => ({
                    code: x.Code,
                    symbol: `${x.Code}.US`,
                    name: x.Name || x.Code
                }));

        symbolCache.us = symbols;
        symbolCacheTime.us = now;

        console.log(
            `US: ${symbols.length} سهم`
        );

        return symbols;

    } catch (err) {

        console.log(
            "US EODHD:",
            err.message
        );

        return symbolCache.us;
    }
}

// ============================================================
// 🪙 CRYPTO
// ============================================================

async function getCryptoSymbols() {

    const now = Date.now();

    if (
        symbolCache.crypto.length > 0 &&
        now - symbolCacheTime.crypto <
        60 * 60 * 1000
    ) {
        return symbolCache.crypto;
    }

    try {

        console.log(
            "CRYPTO: تحميل قائمة العملات"
        );

        const data =
            await eodhd(
                "exchange-symbol-list/CC"
            );

        if (!Array.isArray(data)) {
            return [];
        }

        const symbols =
            data
                .filter(x => x && x.Code)
                .map(x => ({
                    code: x.Code,
                    symbol: `${x.Code}.CC`,
                    name: x.Name || x.Code
                }));

        symbolCache.crypto = symbols;
        symbolCacheTime.crypto = now;

        console.log(
            `CRYPTO: ${symbols.length} زوج`
        );

        return symbols;

    } catch (err) {

        console.log(
            "CRYPTO EODHD:",
            err.message
        );

        return symbolCache.crypto;
    }
}

// ============================================================
// 📈 EOD HISTORY
// ============================================================

async function getHistory(symbol) {

    try {

        const date =
            new Date();

        date.setUTCDate(
            date.getUTCDate() - 250
        );

        const from =
            date
                .toISOString()
                .slice(0, 10);

        const data =
            await eodhd(
                `eod/${encodeURIComponent(symbol)}`,
                {
                    period: "d",
                    order: "a",
                    from
                }
            );

        return Array.isArray(data)
            ? data
            : [];

    } catch (err) {

        console.log(
            `History ${symbol}:`,
            err.message
        );

        return [];
    }
}

// ============================================================
// 📐 EMA
// ============================================================

function calculateEMA(values, period) {

    if (
        values.length < period
    ) {
        return null;
    }

    const multiplier =
        2 / (period + 1);

    let ema =
        values
            .slice(0, period)
            .reduce(
                (a, b) => a + b,
                0
            ) / period;

    for (
        let i = period;
        i < values.length;
        i++
    ) {

        ema =
            (
                values[i] - ema
            ) *
            multiplier +
            ema;
    }

    return ema;
}

// ============================================================
// 📊 RSI
// ============================================================

function calculateRSI(
    values,
    period = 14
) {

    if (
        values.length <= period
    ) {
        return null;
    }

    let gain = 0;
    let loss = 0;

    for (
        let i = 1;
        i <= period;
        i++
    ) {

        const diff =
            values[i] - values[i - 1];

        if (diff >= 0) {
            gain += diff;
        } else {
            loss += Math.abs(diff);
        }
    }

    let avgGain =
        gain / period;

    let avgLoss =
        loss / period;

    for (
        let i = period + 1;
        i < values.length;
        i++
    ) {

        const diff =
            values[i] - values[i - 1];

        const currentGain =
            diff > 0 ? diff : 0;

        const currentLoss =
            diff < 0
                ? Math.abs(diff)
                : 0;

        avgGain =
            (
                avgGain * (period - 1) +
                currentGain
            ) / period;

        avgLoss =
            (
                avgLoss * (period - 1) +
                currentLoss
            ) / period;
    }

    if (avgLoss === 0) {
        return 100;
    }

    const rs =
        avgGain / avgLoss;

    return 100 - (
        100 / (1 + rs)
    );
}

// ============================================================
// 📏 ATR
// ============================================================

function calculateATR(
    candles,
    period = 14
) {

    if (
        candles.length <= period
    ) {
        return null;
    }

    const ranges = [];

    for (
        let i = 1;
        i < candles.length;
        i++
    ) {

        const high =
            Number(candles[i].high);

        const low =
            Number(candles[i].low);

        const previousClose =
            Number(
                candles[i - 1].close
            );

        ranges.push(
            Math.max(
                high - low,
                Math.abs(
                    high - previousClose
                ),
                Math.abs(
                    low - previousClose
                )
            )
        );
    }

    let result =
        ranges
            .slice(0, period)
            .reduce(
                (a, b) => a + b,
                0
            ) / period;

    for (
        let i = period;
        i < ranges.length;
        i++
    ) {

        result =
            (
                result * (period - 1) +
                ranges[i]
            ) / period;
    }

    return result;
}

// ============================================================
// 🔊 VOLUME STRENGTH
// ============================================================

function calculateVolumeStrength(
    candles
) {

    if (
        candles.length < 21
    ) {
        return 1;
    }

    const current =
        Number(
            candles[
                candles.length - 1
            ].volume
        );

    const previous =
        candles
            .slice(-21, -1)
            .map(x => Number(x.volume))
            .filter(Number.isFinite);

    if (!previous.length) {
        return 1;
    }

    const average =
        previous.reduce(
            (a, b) => a + b,
            0
        ) / previous.length;

    if (!average) {
        return 1;
    }

    return current / average;
}

// ============================================================
// 🟦 SUPPORT / 🟥 RESISTANCE
// ============================================================

function calculateLevels(candles) {

    const recent =
        candles.slice(-30);

    const lows =
        recent
            .map(x => Number(x.low))
            .filter(Number.isFinite);

    const highs =
        recent
            .map(x => Number(x.high))
            .filter(Number.isFinite);

    return {
        support:
            lows.length
                ? Math.min(...lows)
                : null,

        resistance:
            highs.length
                ? Math.max(...highs)
                : null
    };
}

// ============================================================
// 🧠 AI ANALYSIS
// ============================================================

function analyze(candles) {

    if (
        candles.length < 60
    ) {
        return null;
    }

    const close =
        candles
            .map(x => Number(x.close))
            .filter(Number.isFinite);

    const price =
        close[close.length - 1];

    const previous =
        close[close.length - 2];

    const ema8 =
        calculateEMA(close, 8);

    const ema21 =
        calculateEMA(close, 21);

    const ema50 =
        calculateEMA(close, 50);

    const rsi =
        calculateRSI(close, 14);

    const atr =
        calculateATR(candles, 14);

    const volume =
        calculateVolumeStrength(candles);

    const levels =
        calculateLevels(candles);

    const change =
        previous
            ? (
                (price - previous) /
                previous
            ) * 100
            : 0;

    let score = 0;

    if (price > ema8) score += 1;
    if (price < ema8) score -= 1;

    if (ema8 > ema21) score += 2;
    if (ema8 < ema21) score -= 2;

    if (ema21 > ema50) score += 2;
    if (ema21 < ema50) score -= 2;

    if (rsi >= 50) score += 1;
    if (rsi < 50) score -= 1;

    if (volume >= 1.2) {
        score += change >= 0 ? 1 : -1;
    }

    let signal =
        "محايد";

    if (
        score >= 5 &&
        rsi >= 55
    ) {
        signal = "شراء قوي";
    }

    if (
        score <= -5 &&
        rsi <= 45
    ) {
        signal = "بيع قوي";
    }

    const buyPower =
        Math.max(
            0,
            Math.min(
                100,
                50 + score * 6
            )
        );

    const sellPower =
        100 - buyPower;

    return {
        price,
        change,
        ema8,
        ema21,
        ema50,
        rsi,
        atr,
        volume,
        support: levels.support,
        resistance: levels.resistance,
        buyPower,
        sellPower,
        score,
        signal
    };
}

// ============================================================
// 🎯 8 ATR TARGETS
// ============================================================

function targets(
    price,
    atr,
    direction
) {

    const multipliers = [
        1,
        1.5,
        2,
        2.5,
        3,
        3.5,
        4,
        5
    ];

    return multipliers.map(
        (m, index) => {

            const target =
                direction === "BUY"
                    ? price + atr * m
                    : price - atr * m;

            return {
                name: `TP${index + 1}`,
                value: target
            };
        }
    );
}

// ============================================================
// 🔢 NUMBER
// ============================================================

function number(value) {

    if (
        value === null ||
        value === undefined ||
        !Number.isFinite(value)
    ) {
        return "-";
    }

    if (
        Math.abs(value) >= 1000
    ) {
        return value.toLocaleString(
            "en-US",
            {
                maximumFractionDigits: 2
            }
        );
    }

    return value.toFixed(4);
}

// ============================================================
// 📩 SIGNAL MESSAGE
// ============================================================

function makeSignal(
    market,
    stock,
    data
) {

    const buy =
        data.signal === "شراء قوي";

    const direction =
        buy
            ? "🟢⬆️ شراء قوي"
            : "🔴⬇️ بيع قوي";

    const tp =
        targets(
            data.price,
            data.atr,
            buy ? "BUY" : "SELL"
        );

    let targetText = "";

    for (const t of tp) {

        targetText +=
            `${t.name}: ${number(t.value)}\n`;
    }

    let marketText;

    if (market === "us") {
        marketText = "🇺🇸 السوق الأمريكي";
    }

    else if (market === "crypto") {
        marketText = "🪙 العملات الرقمية";
    }

    else {
        marketText = "🇸🇦 السوق السعودي";
    }

    return `💀🚀 AI PRO MAX SIGNAL

${marketText}

${stock.code}
${stock.name}

${direction}

💰 السعر:
${number(data.price)}

📈 التغير:
${data.change.toFixed(2)}%

💪 قوة الإشارة:
${Math.abs(data.score * 10)}%

🟢 قوة الشراء:
${data.buyPower.toFixed(0)}%

🔴 قوة البيع:
${data.sellPower.toFixed(0)}%

🔊 قوة الحجم:
${data.volume.toFixed(2)}x

📐 EMA 8:
${number(data.ema8)}

📐 EMA 21:
${number(data.ema21)}

📐 EMA 50:
${number(data.ema50)}

📊 RSI 14:
${data.rsi.toFixed(2)}

📏 ATR 14:
${number(data.atr)}

🟦 الدعم:
${number(data.support)}

🟥 المقاومة:
${number(data.resistance)}

🎯 أهداف ATR:

${targetText}

📡 مصدر البيانات:
EODHD فقط`;
}

// ============================================================
// 📤 SEND
// ============================================================

async function sendSignal(
    market,
    message
) {

    let bot;

    if (market === "tasi") {
        bot = tasiBot;
    }

    if (market === "us") {
        bot = usBot;
    }

    if (market === "crypto") {
        bot = cryptoBot;
    }

    if (!bot) return;

    for (
        const chatId of chats[market]
    ) {

        try {

            await bot.sendMessage(
                chatId,
                message
            );

        } catch (err) {

            console.log(
                "Telegram:",
                err.message
            );
        }
    }
}

// ============================================================
// 🛡️ DUPLICATE SIGNAL PROTECTION
// ============================================================

const lastSignals = new Map();

function duplicate(
    market,
    symbol,
    signal
) {

    const key =
        `${market}:${symbol}:${signal}`;

    const old =
        lastSignals.get(key);

    if (
        old &&
        Date.now() - old <
        30 * 60 * 1000
    ) {
        return true;
    }

    lastSignals.set(
        key,
        Date.now()
    );

    return false;
}

// ============================================================
// 🔍 SCAN MARKET
// ============================================================

async function scanMarket(
    market,
    symbols
) {

    if (!symbols.length) {

        console.log(
            `${market.toUpperCase()}: لا توجد رموز للفحص`
        );

        return;
    }

    // نحلل مجموعة محدودة في كل دورة
    // حتى لا نستهلك API بشكل غير ضروري.

    const selected =
        symbols.slice(0, 10);

    for (
        const stock of selected
    ) {

        const candles =
            await getHistory(
                stock.symbol
            );

        if (!candles.length) {
            continue;
        }

        const result =
            analyze(candles);

        if (!result) {
            continue;
        }

        if (
            result.signal !== "شراء قوي" &&
            result.signal !== "بيع قوي"
        ) {
            continue;
        }

        const direction =
            result.signal === "شراء قوي"
                ? "BUY"
                : "SELL";

        if (
            duplicate(
                market,
                stock.symbol,
                direction
            )
        ) {
            continue;
        }

        const message =
            makeSignal(
                market,
                stock,
                result
            );

        await sendSignal(
            market,
            message
        );
    }
}

// ============================================================
// 🇸🇦 TASI
// ============================================================

async function scanTASI() {

    /*
     * TASI متروك هنا مستقلًا.
     * لا نخترع مصدرًا آخر للبيانات.
     * EODHD هو مصدر البيانات الوحيد.
     */

    console.log(
        "TASI: جاهز للفحص"
    );
}

// ============================================================
// 🚀 MAIN SCAN
// ============================================================

let scanNumber = 0;
let running = false;

async function scan() {

    if (running) {
        return;
    }

    running = true;

    scanNumber++;

    console.log("");
    console.log(
        "===================================="
    );

    console.log(
        `💀🚀 AI PRO MAX SCAN #${scanNumber}`
    );

    try {

        await scanTASI();

        const us =
            await getUSSymbols();

        await scanMarket(
            "us",
            us
        );

        const crypto =
            await getCryptoSymbols();

        await scanMarket(
            "crypto",
            crypto
        );

    } catch (err) {

        console.log(
            "Scan:",
            err.message
        );

    } finally {

        console.log(
            "الفحص مكتمل"
        );

        console.log(
            "===================================="
        );

        running = false;
    }
}

// ============================================================
// 🚀 START
// ============================================================

app.listen(
    PORT,
    async () => {

        console.log("");
        console.log(
            "💀🚀 AI PRO MAX"
        );

        console.log(
            "🤖 TASI BOT:",
            tasiBot ? "ON" : "OFF"
        );

        console.log(
            "🤖 US BOT:",
            usBot ? "ON" : "OFF"
        );

        console.log(
            "🤖 CRYPTO BOT:",
            cryptoBot ? "ON" : "OFF"
        );

        console.log(
            "🟢 النظام يعمل 24/7"
        );

        console.log(
            "⏱️ الفحص كل دقيقتين"
        );

        console.log(
            "📡 EODHD فقط"
        );

        await setupWebhook(
            tasiBot,
            "tasi"
        );

        await setupWebhook(
            usBot,
            "us"
        );

        await setupWebhook(
            cryptoBot,
            "crypto"
        );

        // أول فحص
        setTimeout(
            scan,
            10000
        );

        // فحص كل دقيقتين
        setInterval(
            scan,
            SCAN_EVERY
        );
    }
);