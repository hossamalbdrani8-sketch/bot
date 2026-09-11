
// ============================================================
// 🤖 AI PRO MAX 💀🚀
// TASI + US + CRYPTO — 3 TELEGRAM BOTS
// Node.js 18+
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ الإعدادات الموجودة في Railway
// ============================================================

const EODHD_API_KEY = process.env.EODHD_API_KEY || "";

const TASI_CONFIG = process.env.TASI_CONFIG || "";
const US_CONFIG = process.env.US_CONFIG || "";
const CRYPTO_CONFIG = process.env.CRYPTO_CONFIG || "";

// ============================================================
// ⚙️ إعدادات التشغيل
// ============================================================

const PORT = Number(process.env.PORT || 8080);

const SCAN_MINUTES = Number(process.env.SCAN_MINUTES || 5);

const MIN_US_PRICE = 0.20;

// عدد الأسهم التي يتم تحليلها في كل دورة
// حتى لا يتم استهلاك API بسرعة كبيرة
const SYMBOLS_PER_CYCLE =
    Number(process.env.SYMBOLS_PER_CYCLE || 20);

// ============================================================
// 🌐 EXPRESS
// ============================================================

const app = express();

app.get("/", (req, res) => {
    res.json({
        status: "online",
        bot: "AI PRO MAX 💀🚀",
        markets: ["TASI", "US", "CRYPTO"],
        time: new Date().toISOString()
    });
});

app.get("/health", (req, res) => {
    res.json({
        status: "healthy",
        eodhd: Boolean(EODHD_API_KEY),
        tasi: Boolean(TASI_CONFIG),
        us: Boolean(US_CONFIG),
        crypto: Boolean(CRYPTO_CONFIG)
    });
});

app.listen(PORT, "0.0.0.0", () => {
    console.log(`🌐 الخادم يعمل على ${PORT}`);
});

// ============================================================
// 🔐 استخراج توكن Telegram
// ============================================================

function getTelegramToken(value) {
    if (!value) return "";

    const text = String(value).trim();

    // إذا كانت القيمة JSON
    if (text.startsWith("{")) {
        try {
            const obj = JSON.parse(text);

            return (
                obj.token ||
                obj.telegramToken ||
                obj.TELEGRAM_TOKEN ||
                obj.botToken ||
                ""
            );
        } catch (err) {
            return "";
        }
    }

    // إذا كانت القيمة توكن مباشر
    return text;
}

// ============================================================
// 🤖 التوكنات الثلاثة
// ============================================================

const TASI_TOKEN = getTelegramToken(TASI_CONFIG);
const US_TOKEN = getTelegramToken(US_CONFIG);
const CRYPTO_TOKEN = getTelegramToken(CRYPTO_CONFIG);

// ============================================================
// 📱 البوتات
// ============================================================

let tasiBot = null;
let usBot = null;
let cryptoBot = null;

// ============================================================
// 💬 Chat IDs
// ============================================================

let tasiChatId = null;
let usChatId = null;
let cryptoChatId = null;

// ============================================================
// 🧠 أدوات عامة
// ============================================================

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function num(v) {
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
}

function money(v) {
    const n = num(v);

    if (n >= 1000) {
        return n.toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
    }

    return n.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

function percent(v) {
    return `${num(v).toFixed(2)}%`;
}

function formatVolume(v) {
    const n = num(v);

    if (n >= 1_000_000_000) {
        return `${(n / 1_000_000_000).toFixed(2)}B`;
    }

    if (n >= 1_000_000) {
        return `${(n / 1_000_000).toFixed(2)}M`;
    }

    if (n >= 1_000) {
        return `${(n / 1_000).toFixed(2)}K`;
    }

    return n.toFixed(0);
}

// ============================================================
// 📊 EODHD REQUEST
// ============================================================

async function eodhd(path, params = {}) {

    if (!EODHD_API_KEY) {
        throw new Error("EODHD_API_KEY غير موجود");
    }

    const query = new URLSearchParams({
        ...params,
        api_token: EODHD_API_KEY,
        fmt: "json"
    });

    const url =
        `https://eodhd.com/api/${path}?${query.toString()}`;

    const response = await fetch(url);

    const text = await response.text();

    if (!response.ok) {
        throw new Error(
            `EODHD HTTP ${response.status}: ${text.slice(0, 250)}`
        );
    }

    try {
        return JSON.parse(text);
    } catch {
        throw new Error("EODHD أرسل بيانات غير صالحة");
    }
}

// ============================================================
// 📈 EMA
// ============================================================

function calculateEMA(values, period) {

    if (!values || values.length === 0) {
        return 0;
    }

    const k = 2 / (period + 1);

    let ema = values[0];

    for (let i = 1; i < values.length; i++) {
        ema =
            values[i] * k +
            ema * (1 - k);
    }

    return ema;
}

// ============================================================
// 📉 RSI
// ============================================================

function calculateRSI(values, period = 14) {

    if (!values || values.length <= period) {
        return 50;
    }

    let gains = 0;
    let losses = 0;

    for (let i = 1; i <= period; i++) {

        const diff =
            values[i] - values[i - 1];

        if (diff >= 0) {
            gains += diff;
        } else {
            losses += Math.abs(diff);
        }
    }

    let avgGain = gains / period;
    let avgLoss = losses / period;

    for (let i = period + 1; i < values.length; i++) {

        const diff =
            values[i] - values[i - 1];

        const gain =
            diff > 0 ? diff : 0;

        const loss =
            diff < 0 ? Math.abs(diff) : 0;

        avgGain =
            ((avgGain * (period - 1)) + gain) /
            period;

        avgLoss =
            ((avgLoss * (period - 1)) + loss) /
            period;
    }

    if (avgLoss === 0) {
        return 100;
    }

    const rs = avgGain / avgLoss;

    return 100 - (100 / (1 + rs));
}

// ============================================================
// 📐 ATR 14
// ============================================================

function calculateATR(candles, period = 14) {

    if (!candles || candles.length < period + 1) {
        return 0;
    }

    const tr = [];

    for (let i = 1; i < candles.length; i++) {

        const high = num(candles[i].high);
        const low = num(candles[i].low);
        const prevClose =
            num(candles[i - 1].close);

        const range1 =
            high - low;

        const range2 =
            Math.abs(high - prevClose);

        const range3 =
            Math.abs(low - prevClose);

        tr.push(
            Math.max(range1, range2, range3)
        );
    }

    if (tr.length < period) {
        return 0;
    }

    let atr = 0;

    for (let i = 0; i < period; i++) {
        atr += tr[i];
    }

    atr /= period;

    for (let i = period; i < tr.length; i++) {
        atr =
            ((atr * (period - 1)) + tr[i]) /
            period;
    }

    return atr;
}

// ============================================================
// 🧱 الدعم والمقاومة
// ============================================================

function supportResistance(candles) {

    if (!candles || candles.length < 20) {
        return {
            support: 0,
            resistance: 0
        };
    }

    const recent =
        candles.slice(-30);

    let support = Infinity;
    let resistance = 0;

    for (const c of recent) {

        const low = num(c.low);
        const high = num(c.high);

        if (low > 0 && low < support) {
            support = low;
        }

        if (high > resistance) {
            resistance = high;
        }
    }

    if (!Number.isFinite(support)) {
        support = 0;
    }

    return {
        support,
        resistance
    };
}

// ============================================================
// 🎯 8 أهداف ATR
// ============================================================

function atrTargets(price, atr) {

    const multipliers = [
        0.5,
        1,
        1.5,
        2,
        2.5,
        3,
        4,
        5
    ];

    return multipliers.map((m, index) => {

        return {
            name: `TP${index + 1}`,
            price: price + (atr * m)
        };

    });
}

// ============================================================
// 🧠 AI TREND ENGINE
// ============================================================

function analyzeMarket(candles) {

    if (!candles || candles.length < 30) {
        return null;
    }

    const closes =
        candles
            .map(c => num(c.close))
            .filter(v => v > 0);

    if (closes.length < 30) {
        return null;
    }

    const price =
        closes[closes.length - 1];

    const ema8 =
        calculateEMA(closes, 8);

    const ema21 =
        calculateEMA(closes, 21);

    const ema50 =
        calculateEMA(closes, 50);

    const rsi =
        calculateRSI(closes, 14);

    const atr =
        calculateATR(candles, 14);

    const sr =
        supportResistance(candles);

    let score = 50;

    if (price > ema8) score += 8;
    else score -= 8;

    if (ema8 > ema21) score += 10;
    else score -= 10;

    if (ema21 > ema50) score += 12;
    else score -= 12;

    if (rsi >= 50) score += 10;
    else score -= 10;

    score =
        Math.max(0, Math.min(100, score));

    let signal = "مراقبة";

    if (
        score >= 80 &&
        rsi < 80
    ) {
        signal = "شراء قوي 🟢";
    }
    else if (
        score >= 65
    ) {
        signal = "شراء 🟢";
    }
    else if (
        score <= 25
    ) {
        signal = "بيع قوي 🔴";
    }
    else if (
        score <= 40
    ) {
        signal = "بيع 🔴";
    }

    return {
        price,
        ema8,
        ema21,
        ema50,
        rsi,
        atr,
        score,
        signal,
        support: sr.support,
        resistance: sr.resistance,
        targets: atrTargets(price, atr)
    };
}

// ============================================================
// 📊 بيانات سهم / عملة
// ============================================================

async function getIntraday(symbol) {

    return await eodhd(
        `intraday/${encodeURIComponent(symbol)}`,
        {
            interval: "5m",
            fmt: "json"
        }
    );
}

// ============================================================
// 🇸🇦 قائمة TASI
// ============================================================

async function getTasiUniverse() {

    const data =
        await eodhd("exchange-symbol-list/TADAWUL");

    if (!Array.isArray(data)) {
        return [];
    }

    return data
        .filter(x =>
            x &&
            x.Code &&
            (
                x.Type === "Common Stock" ||
                x.Type === "Stock" ||
                !x.Type
            )
        )
        .map(x => ({
            code: String(x.Code),
            name: x.Name || x.Code,
            exchange: x.Exchange || "TADAWUL"
        }));
}

// ============================================================
// 🇺🇸 قائمة السوق الأمريكي
// ============================================================

async function getUSUniverse() {

    const data =
        await eodhd("exchange-symbol-list/US");

    if (!Array.isArray(data)) {
        return [];
    }

    return data
        .filter(x => {

            if (!x || !x.Code) {
                return false;
            }

            const exchange =
                String(x.Exchange || "").toUpperCase();

            return (
                exchange.includes("NASDAQ") ||
                exchange === "US"
            );
        })
        .map(x => ({
            code: String(x.Code),
            name: x.Name || x.Code,
            exchange: x.Exchange || "NASDAQ"
        }));
}

// ============================================================
// 🪙 قائمة العملات
// ============================================================

async function getCryptoUniverse() {

    const data =
        await eodhd("exchange-symbol-list/CC");

    if (!Array.isArray(data)) {
        return [];
    }

    return data
        .filter(x => x && x.Code)
        .map(x => ({
            code: String(x.Code),
            name: x.Name || x.Code
        }));
}

// ============================================================
// 📱 رسالة الإشارة
// ============================================================

function buildSignalMessage(
    market,
    item,
    analysis
) {

    let text = "";

    text += `💀🚀 AI PRO MAX\n`;
    text += `━━━━━━━━━━━━━━━━━━\n`;

    if (market === "TASI") {
        text += `🇸🇦 السوق السعودي\n`;
    }
    else if (market === "US") {
        text += `🇺🇸 السوق الأمريكي\n`;
    }
    else {
        text += `🪙 العملات الرقمية\n`;
    }

    text += `\n`;

    text += `📌 الرمز: ${item.code}\n`;
    text += `💰 السعر: ${money(analysis.price)}\n`;
    text += `📊 الإشارة: ${analysis.signal}\n`;
    text += `🧠 قوة الاتجاه: ${analysis.score}/100\n`;

    text += `\n`;

    text += `📈 EMA8: ${money(analysis.ema8)}\n`;
    text += `📈 EMA21: ${money(analysis.ema21)}\n`;
    text += `📈 EMA50: ${money(analysis.ema50)}\n`;

    text += `\n`;

    text += `📉 RSI14: ${analysis.rsi.toFixed(2)}\n`;
    text += `🔥 ATR14: ${money(analysis.atr)}\n`;

    text += `\n`;

    text += `🟢 الدعم: ${money(analysis.support)}\n`;
    text += `🔴 المقاومة: ${money(analysis.resistance)}\n`;

    text += `\n`;
    text += `🎯 أهداف ATR:\n`;

    for (const target of analysis.targets) {
        text +=
            `${target.name}: ${money(target.price)}\n`;
    }

    text += `\n`;
    text += `━━━━━━━━━━━━━━━━━━\n`;
    text += `🤖 فحص تلقائي AI PRO MAX`;

    return text;
}

// ============================================================
// 📤 إرسال Telegram
// ============================================================

async function sendTelegram(
    bot,
    chatId,
    message
) {

    if (!bot || !chatId) {
        return false;
    }

    try {

        await bot.sendMessage(
            chatId,
            message
        );

        return true;

    } catch (err) {

        console.error(
            "❌ خطأ Telegram:",
            err.message
        );

        return false;
    }
}

// ============================================================
// 🤖 إنشاء بوت مستقل
// ============================================================

function createTelegramBot(
    name,
    token,
    onChatId
) {

    if (!token) {

        console.error(
            `❌ ${name}: التوكن غير موجود`
        );

        return null;
    }

    try {

        const bot =
            new TelegramBot(
                token,
                {
                    polling: true
                }
            );

        console.log(
            `🤖 ${name}: تم تشغيل البوت`
        );

        bot.onText(
            /^\/start$/i,
            async msg => {

                const chatId =
                    msg.chat.id;

                onChatId(chatId);

                console.log(
                    `📱 ${name}: تم تسجيل Chat ID`
                );

                await bot.sendMessage(
                    chatId,
                    `💀🚀 أهلاً بك في AI PRO MAX\n\n` +
                    `✅ البوت يعمل الآن\n` +
                    `🔄 الفحص تلقائي\n` +
                    `📊 السوق: ${name}\n\n` +
                    `لن تحتاج إلى تشغيل الفحص يدويًا.`
                );
            }
        );

        bot.onText(
            /^\/status$/i,
            async msg => {

                await bot.sendMessage(
                    msg.chat.id,
                    `💀🚀 AI PRO MAX\n\n` +
                    `✅ البوت متصل\n` +
                    `🔄 الفحص: تلقائي\n` +
                    `⏱️ الدورة: كل ${SCAN_MINUTES} دقائق`
                );
            }
        );

        bot.on(
            "polling_error",
            error => {

                console.error(
                    `❌ Telegram ${name}:`,
                    error.message
                );
            }
        );

        return bot;

    } catch (err) {

        console.error(
            `❌ فشل تشغيل ${name}:`,
            err.message
        );

        return null;
    }
}

// ============================================================
// 🚀 تشغيل البوتات الثلاثة
// ============================================================

console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
console.log("💀🚀 AI PRO MAX يبدأ التشغيل");
console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

if (!EODHD_API_KEY) {
    console.error("❌ EODHD_API_KEY غير موجود");
} else {
    console.log("✅ EODHD_API_KEY موجود");
}

tasiBot = createTelegramBot(
    "TASI 🇸🇦",
    TASI_TOKEN,
    chatId => {
        tasiChatId = chatId;
    }
);

usBot = createTelegramBot(
    "US 🇺🇸",
    US_TOKEN,
    chatId => {
        usChatId = chatId;
    }
);

cryptoBot = createTelegramBot(
    "CRYPTO 🪙",
    CRYPTO_TOKEN,
    chatId => {
        cryptoChatId = chatId;
    }
);

// ============================================================
// 📊 حالة الأسواق
// ============================================================

let tasiUniverse = [];
let usUniverse = [];
let cryptoUniverse = [];

let tasiIndex = 0;
let usIndex = 0;
let cryptoIndex = 0;

// منع تكرار نفس الإشارة باستمرار
const lastSignals = new Map();

// ============================================================
// 🔄 جلب القوائم
// ============================================================

async function refreshUniverses() {

    console.log("🔄 تحديث قوائم الأسواق...");

    try {

        tasiUniverse =
            await getTasiUniverse();

        console.log(
            `🇸🇦 TASI: ${tasiUniverse.length} سهم`
        );

    } catch (err) {

        console.error(
            "❌ خطأ قائمة TASI:",
            err.message
        );
    }

    try {

        usUniverse =
            await getUSUniverse();

        console.log(
            `🇺🇸 US/NASDAQ: ${usUniverse.length} سهم`
        );

    } catch (err) {

        console.error(
            "❌ خطأ قائمة US:",
            err.message
        );
    }

    try {

        cryptoUniverse =
            await getCryptoUniverse();

        console.log(
            `🪙 CRYPTO: ${cryptoUniverse.length} عملة`
        );

    } catch (err) {

        console.error(
            "❌ خطأ قائمة CRYPTO:",
            err.message
        );
    }
}

// ============================================================
// 🔎 فحص عنصر
// ============================================================

async function scanItem(
    market,
    item,
    bot,
    chatId
) {

    try {

        let symbol = item.code;

        if (market === "TASI") {

            symbol =
                `${item.code}.${item.exchange || "TADAWUL"}`;
        }

        else if (market === "US") {

            symbol =
                `${item.code}.US`;
        }

        // CRYPTO يستخدم الرمز كما هو
        // مثال BTC-USD.CC

        const candles =
            await getIntraday(symbol);

        if (!Array.isArray(candles)) {
            return;
        }

        if (candles.length < 30) {
            return;
        }

        const analysis =
            analyzeMarket(candles);

        if (!analysis) {
            return;
        }

        // السعر الأمريكي يجب أن يكون 0.20 فأعلى
        if (
            market === "US" &&
            analysis.price < MIN_US_PRICE
        ) {
            return;
        }

        // نرسل فقط إشارات الشراء
        if (
            analysis.signal !== "شراء قوي 🟢" &&
            analysis.signal !== "شراء 🟢"
        ) {
            return;
        }

        const key =
            `${market}:${item.code}`;

        const signalKey =
            `${analysis.signal}:${Math.round(analysis.score / 5)}`;

        if (
            lastSignals.get(key) === signalKey
        ) {
            return;
        }

        lastSignals.set(
            key,
            signalKey
        );

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

        console.log(
            `🚨 ${market} ${item.code} → ${analysis.signal}`
        );

    } catch (err) {

        console.error(
            `❌ ${market} ${item.code}:`,
            err.message
        );
    }
}

// ============================================================
// 🔄 فحص دورة واحدة
// ============================================================

async function scanCycle() {

    console.log(
        `🔄 بدء دورة الفحص ${new Date().toLocaleString("ar-SA")}`
    );

    // --------------------------------------------------------
    // 🇸🇦 TASI
    // --------------------------------------------------------

    if (
        tasiBot &&
        tasiChatId &&
        tasiUniverse.length
    ) {

        const batch =
            tasiUniverse.slice(
                tasiIndex,
                tasiIndex + SYMBOLS_PER_CYCLE
            );

        for (const item of batch) {

            await scanItem(
                "TASI",
                item,
                tasiBot,
                tasiChatId
            );

            await sleep(350);
        }

        tasiIndex +=
            SYMBOLS_PER_CYCLE;

        if (
            tasiIndex >= tasiUniverse.length
        ) {
            tasiIndex = 0;

            console.log(
                "🔁 اكتمل مرور TASI وسيبدأ من جديد"
            );
        }
    }

    // --------------------------------------------------------
    // 🇺🇸 US
    // --------------------------------------------------------

    if (
        usBot &&
        usChatId &&
        usUniverse.length
    ) {

        const batch =
            usUniverse.slice(
                usIndex,
                usIndex + SYMBOLS_PER_CYCLE
            );

        for (const item of batch) {

            await scanItem(
                "US",
                item,
                usBot,
                usChatId
            );

            await sleep(350);
        }

        usIndex +=
            SYMBOLS_PER_CYCLE;

        if (
            usIndex >= usUniverse.length
        ) {
            usIndex = 0;

            console.log(
                "🔁 اكتمل مرور US وسيبدأ من جديد"
            );
        }
    }

    // --------------------------------------------------------
    // 🪙 CRYPTO
    // --------------------------------------------------------

    if (
        cryptoBot &&
        cryptoChatId &&
        cryptoUniverse.length
    ) {

        const batch =
            cryptoUniverse.slice(
                cryptoIndex,
                cryptoIndex + SYMBOLS_PER_CYCLE
            );

        for (const item of batch) {

            await scanItem(
                "CRYPTO",
                item,
                cryptoBot,
                cryptoChatId
            );

            await sleep(350);
        }

        cryptoIndex +=
            SYMBOLS_PER_CYCLE;

        if (
            cryptoIndex >= cryptoUniverse.length
        ) {
            cryptoIndex = 0;

            console.log(
                "🔁 اكتمل مرور CRYPTO وسيبدأ من جديد"
            );
        }
    }

    console.log("✅ انتهت دورة الفحص");
}

// ============================================================
// 🔄 التشغيل التلقائي
// ============================================================

async function startSystem() {

    await refreshUniverses();

    console.log(
        `⏱️ الفحص التلقائي كل ${SCAN_MINUTES} دقائق`
    );

    // أول فحص بعد تحميل القوائم
    setTimeout(
        () => {
            scanCycle().catch(err => {
                console.error(
                    "❌ خطأ دورة الفحص:",
                    err.message
                );
            });
        },
        5000
    );

    // الفحص المستمر
    setInterval(
        () => {

            scanCycle().catch(err => {

                console.error(
                    "❌ خطأ دورة الفحص:",
                    err.message
                );

            });

        },
        SCAN_MINUTES * 60 * 1000
    );

    // تحديث القوائم كل ساعة
    setInterval(
        () => {

            refreshUniverses().catch(err => {

                console.error(
                    "❌ خطأ تحديث القوائم:",
                    err.message
                );

            });

        },
        60 * 60 * 1000
    );
}

// ============================================================
// ▶️ بدء النظام
// ============================================================

startSystem().catch(err => {

    console.error(
        "❌ خطأ تشغيل النظام:",
        err.message
    );

});