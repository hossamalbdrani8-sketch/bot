
"use strict";

/*
============================================================
🤖 AI PRO MAX 💀🚀
بوت تليجرام مستقل للفحص:
🇸🇦 TASI
🇺🇸 US / NASDAQ
🪙 CRYPTO
============================================================

المتطلبات:
- Node.js 18+
- TELEGRAM_TOKEN
- EODHD_API_KEY

المتغيرات الموجودة عندك تبقى كما هي.
============================================================
*/

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ الإعدادات
// ============================================================

const PORT = Number(process.env.PORT || 8080);

const TELEGRAM_TOKEN =
    process.env.TELEGRAM_TOKEN ||
    process.env.TELEGRAM_BOT_TOKEN ||
    process.env.BOT_TOKEN ||
    "";

const EODHD_API_KEY =
    process.env.EODHD_API_KEY ||
    process.env.EODHD_TOKEN ||
    process.env.EODHD_API_TOKEN ||
    process.env.API_TOKEN ||
    "";

// متغيراتك الحالية — لا نحذفها
const TASI_CONFIG =
    process.env.TASI_CONFIG ||
    process.env.TASI_API ||
    process.env.TASI_TOKEN ||
    "";

const US_CONFIG =
    process.env.US_CONFIG ||
    process.env.US_API ||
    process.env.US_TOKEN ||
    "";

const CRYPTO_CONFIG =
    process.env.CRYPTO_CONFIG ||
    process.env.CRYPTO_API ||
    process.env.CRYPTO_TOKEN ||
    "";

// ============================================================
// 🧠 إعدادات البوت
// ============================================================

const SCAN_INTERVAL = 5 * 60 * 1000; // كل 5 دقائق

const MIN_US_PRICE = 0.20;

// منع إرسال نفس الإشارة بشكل متكرر
const SIGNAL_MEMORY_TIME = 60 * 60 * 1000;

// ============================================================
// 🌐 الخادم
// ============================================================

const app = express();

app.get("/", (req, res) => {
    res.json({
        status: "ONLINE",
        bot: "AI PRO MAX",
        time: new Date().toISOString()
    });
});

app.get("/health", (req, res) => {
    res.json({
        ok: true,
        bot: "AI PRO MAX 💀🚀"
    });
});

app.listen(PORT, () => {
    console.log(`🌐 الخادم يعمل على المنفذ ${PORT}`);
});

// ============================================================
// 🔐 فحص الإعدادات
// ============================================================

console.log("==============================================");
console.log("🤖 AI PRO MAX 💀🚀");
console.log("==============================================");

console.log(
    TELEGRAM_TOKEN
        ? "✅ TELEGRAM_TOKEN موجود"
        : "❌ TELEGRAM_TOKEN غير موجود"
);

console.log(
    EODHD_API_KEY
        ? "✅ EODHD_API_KEY موجود"
        : "❌ EODHD_API_KEY غير موجود"
);

console.log(
    TASI_CONFIG
        ? "✅ إعداد تاسي موجود"
        : "ℹ️ إعداد تاسي غير مستخدم"
);

console.log(
    US_CONFIG
        ? "✅ إعداد الأمريكي موجود"
        : "ℹ️ إعداد الأمريكي غير مستخدم"
);

console.log(
    CRYPTO_CONFIG
        ? "✅ إعداد العملات موجود"
        : "ℹ️ إعداد العملات غير مستخدم"
);

// ============================================================
// 🤖 TELEGRAM
// ============================================================

if (!TELEGRAM_TOKEN) {
    console.error("❌ لا يوجد Telegram Token");
    process.exit(1);
}

const bot = new TelegramBot(TELEGRAM_TOKEN, {
    polling: true
});

// ============================================================
// 👥 المحادثات التي بدأت البوت
// ============================================================

const CHAT_IDS = new Set();

// إذا وضعت Chat ID اختياريًا
if (process.env.TELEGRAM_CHAT_ID) {
    CHAT_IDS.add(String(process.env.TELEGRAM_CHAT_ID));
}

// ============================================================
// 🚀 START
// ============================================================

bot.onText(/^\/start$/, async (msg) => {

    const chatId = String(msg.chat.id);

    CHAT_IDS.add(chatId);

    const text =
`🤖 AI PRO MAX 💀🚀

✅ تم تشغيل البوت بنجاح

🇸🇦 تاسي: فحص تلقائي
🇺🇸 الأمريكي / NASDAQ: فحص تلقائي
🪙 العملات الرقمية: فحص تلقائي

🧠 محرك الاتجاه: AI PRO MAX
📏 ATR(14)
🎯 8 أهداف ديناميكية
📍 دعم ومقاومة
💧 السيولة
📰 الأخبار

⏱ الفحص يعمل تلقائيًا كل 5 دقائق.

لن تحتاج إلى إرسال أمر فحص يدوي.`;

    try {
        await bot.sendMessage(chatId, text);
    } catch (err) {
        console.error("❌ Telegram:", err.message);
    }
});

// ============================================================
// 📡 طلب EODHD
// ============================================================

async function eodhd(path) {

    if (!EODHD_API_KEY) {
        throw new Error("EODHD_API_KEY غير موجود");
    }

    const separator = path.includes("?") ? "&" : "?";

    const url =
        `https://eodhd.com/api/${path}${separator}api_token=${encodeURIComponent(EODHD_API_KEY)}&fmt=json`;

    const response = await fetch(url);

    if (!response.ok) {
        const body = await response.text();

        throw new Error(
            `EODHD HTTP ${response.status} ${body.slice(0, 200)}`
        );
    }

    return await response.json();
}

// ============================================================
// 🧮 حساب EMA
// ============================================================

function ema(values, period) {

    if (!values || values.length < period) {
        return null;
    }

    const multiplier = 2 / (period + 1);

    let result = 0;

    for (let i = 0; i < period; i++) {
        result += Number(values[i]);
    }

    result /= period;

    for (let i = period; i < values.length; i++) {
        result =
            (Number(values[i]) - result) * multiplier + result;
    }

    return result;
}

// ============================================================
// 🧮 ATR(14)
// ============================================================

function calculateATR(candles, period = 14) {

    if (!candles || candles.length < period + 1) {
        return null;
    }

    const trs = [];

    for (let i = 1; i < candles.length; i++) {

        const high = Number(candles[i].high);
        const low = Number(candles[i].low);
        const previousClose = Number(candles[i - 1].close);

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

    let atr = 0;

    for (let i = 0; i < period; i++) {
        atr += trs[i];
    }

    atr /= period;

    for (let i = period; i < trs.length; i++) {
        atr =
            ((atr * (period - 1)) + trs[i]) /
            period;
    }

    return atr;
}

// ============================================================
// 📍 دعم ومقاومة من حركة السعر
// ============================================================

function supportResistance(candles) {

    if (!candles || candles.length < 20) {
        return {
            support: null,
            resistance: null
        };
    }

    const recent = candles.slice(-20);

    let support = Infinity;
    let resistance = -Infinity;

    for (const candle of recent) {

        const low = Number(candle.low);
        const high = Number(candle.high);

        if (Number.isFinite(low)) {
            support = Math.min(support, low);
        }

        if (Number.isFinite(high)) {
            resistance = Math.max(resistance, high);
        }
    }

    return {
        support:
            Number.isFinite(support)
                ? support
                : null,

        resistance:
            Number.isFinite(resistance)
                ? resistance
                : null
    };
}

// ============================================================
// 💧 تحليل السيولة
// ============================================================

function liquidity(candles) {

    if (!candles || candles.length < 10) {
        return {
            volume: 0,
            averageVolume: 0,
            strength: 0
        };
    }

    const last = candles[candles.length - 1];

    const volumes = candles
        .slice(-20)
        .map(x => Number(x.volume))
        .filter(Number.isFinite);

    if (!volumes.length) {
        return {
            volume: 0,
            averageVolume: 0,
            strength: 0
        };
    }

    const average =
        volumes.reduce((a, b) => a + b, 0) /
        volumes.length;

    const volume = Number(last.volume || 0);

    const ratio =
        average > 0
            ? volume / average
            : 0;

    let strength = 0;

    if (ratio >= 3) {
        strength = 100;
    } else if (ratio >= 2) {
        strength = 80;
    } else if (ratio >= 1.5) {
        strength = 65;
    } else if (ratio >= 1) {
        strength = 50;
    } else {
        strength = 25;
    }

    return {
        volume,
        averageVolume: average,
        ratio,
        strength
    };
}

// ============================================================
// 🧠 AI PRO MAX — الاتجاه
// ============================================================

function trendEngine(candles) {

    if (!candles || candles.length < 50) {
        return {
            direction: "محايد",
            bullish: false,
            bearish: false,
            strength: 0
        };
    }

    const closes = candles
        .map(x => Number(x.close))
        .filter(Number.isFinite);

    const e20 = ema(closes, 20);
    const e50 = ema(closes, 50);

    const price = closes[closes.length - 1];

    if (
        e20 === null ||
        e50 === null ||
        !Number.isFinite(price)
    ) {
        return {
            direction: "محايد",
            bullish: false,
            bearish: false,
            strength: 0
        };
    }

    let strength = 0;

    if (price > e20) {
        strength += 30;
    }

    if (e20 > e50) {
        strength += 30;
    }

    if (price > e50) {
        strength += 40;
    }

    if (strength >= 70) {

        return {
            direction: "صاعد",
            bullish: true,
            bearish: false,
            strength
        };
    }

    let bearStrength = 0;

    if (price < e20) {
        bearStrength += 30;
    }

    if (e20 < e50) {
        bearStrength += 30;
    }

    if (price < e50) {
        bearStrength += 40;
    }

    if (bearStrength >= 70) {

        return {
            direction: "هابط",
            bullish: false,
            bearish: true,
            strength: bearStrength
        };
    }

    return {
        direction: "محايد",
        bullish: false,
        bearish: false,
        strength: Math.max(strength, bearStrength)
    };
}

// ============================================================
// 🎯 8 أهداف ATR
// ============================================================

function atrTargets(price, atr, direction) {

    if (
        !Number.isFinite(price) ||
        !Number.isFinite(atr) ||
        atr <= 0
    ) {
        return [];
    }

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

    return multipliers.map((m, index) => {

        const target =
            direction === "صاعد"
                ? price + atr * m
                : price - atr * m;

        return {
            number: index + 1,
            price: target
        };
    });
}

// ============================================================
// 📰 الأخبار
// ============================================================

async function getNews(symbol, exchange) {

    try {

        const data = await eodhd(
            `news?s=${encodeURIComponent(symbol)}&offset=0&limit=3`
        );

        if (!Array.isArray(data)) {
            return [];
        }

        return data.slice(0, 3).map(item => ({

            title:
                item.title ||
                item.headline ||
                "خبر جديد",

            source:
                item.source ||
                item.site ||
                "EODHD",

            date:
                item.date ||
                item.publishedAt ||
                ""

        }));

    } catch (err) {

        console.log(
            `⚠️ الأخبار ${symbol}: ${err.message}`
        );

        return [];
    }
}

// ============================================================
// 🔢 تنسيق الأرقام
// ============================================================

function money(value, digits = 2) {

    if (!Number.isFinite(Number(value))) {
        return "-";
    }

    return Number(value).toFixed(digits);
}

function bigNumber(value) {

    const n = Number(value);

    if (!Number.isFinite(n)) {
        return "-";
    }

    if (Math.abs(n) >= 1_000_000_000) {
        return `${(n / 1_000_000_000).toFixed(2)}B`;
    }

    if (Math.abs(n) >= 1_000_000) {
        return `${(n / 1_000_000).toFixed(2)}M`;
    }

    if (Math.abs(n) >= 1_000) {
        return `${(n / 1_000).toFixed(2)}K`;
    }

    return String(Math.round(n));
}

// ============================================================
// 📊 تحليل سهم
// ============================================================

async function analyzeSymbol(symbol, exchange) {

    const candles = await eodhd(
        `eod/${encodeURIComponent(symbol)}?period=d&order=d&from=2025-01-01`
    );

    if (!Array.isArray(candles) || candles.length < 20) {
        return null;
    }

    const clean = candles
        .filter(c =>
            Number.isFinite(Number(c.close)) &&
            Number.isFinite(Number(c.high)) &&
            Number.isFinite(Number(c.low))
        )
        .sort(
            (a, b) =>
                new Date(a.date) - new Date(b.date)
        );

    if (clean.length < 20) {
        return null;
    }

    const last = clean[clean.length - 1];

    const price = Number(last.close);

    if (!Number.isFinite(price) || price <= 0) {
        return null;
    }

    // 🇺🇸 أقل سعر 0.20$
    if (
        exchange === "US" &&
        price < MIN_US_PRICE
    ) {
        return null;
    }

    const atr = calculateATR(clean, 14);

    const trend = trendEngine(clean);

    const sr = supportResistance(clean);

    const liq = liquidity(clean);

    if (!atr) {
        return null;
    }

    const targets =
        trend.direction === "صاعد" ||
        trend.direction === "هابط"
            ? atrTargets(
                price,
                atr,
                trend.direction
            )
            : [];

    let signal = "⚪ محايد";

    if (
        trend.bullish &&
        liq.strength >= 50
    ) {
        signal = "🟢 شراء قوي";
    } else if (
        trend.bullish
    ) {
        signal = "🟢 اتجاه صاعد";
    } else if (
        trend.bearish &&
        liq.strength >= 50
    ) {
        signal = "🔴✓ هابط";
    } else if (
        trend.bearish
    ) {
        signal = "🔴 اتجاه هابط";
    }

    return {
        symbol,
        exchange,
        price,
        atr,
        trend,
        support: sr.support,
        resistance: sr.resistance,
        liquidity: liq,
        targets,
        signal
    };
}

// ============================================================
// 📋 الحصول على قائمة السوق
// ============================================================

async function getExchangeSymbols(exchange) {

    const data = await eodhd(
        `exchange-symbol-list/${exchange}`
    );

    if (!Array.isArray(data)) {
        throw new Error(
            `قائمة ${exchange} غير صالحة`
        );
    }

    return data;
}

// ============================================================
// 🇸🇦 تاسي
// ============================================================

async function scanTASI() {

    console.log("🇸🇦 بدء فحص تاسي...");

    const symbols =
        await getExchangeSymbols("TADAWUL");

    console.log(
        `🇸🇦 عدد رموز تاسي: ${symbols.length}`
    );

    return scanUniverse(
        symbols,
        "TASI"
    );
}

// ============================================================
// 🇺🇸 الأمريكي
// ============================================================

async function scanUS() {

    console.log(
        "🇺🇸 بدء فحص الأمريكي / NASDAQ..."
    );

    const symbols =
        await getExchangeSymbols("US");

    console.log(
        `🇺🇸 عدد الرموز الأمريكية: ${symbols.length}`
    );

    // جميع الرموز — لا يوجد MAX_SYMBOLS
    return scanUniverse(
        symbols,
        "US"
    );
}

// ============================================================
// 🪙 العملات الرقمية
// ============================================================

async function scanCrypto() {

    console.log(
        "🪙 بدء فحص العملات الرقمية..."
    );

    const symbols =
        await getExchangeSymbols("CC");

    console.log(
        `🪙 عدد العملات: ${symbols.length}`
    );

    return scanUniverse(
        symbols,
        "CRYPTO"
    );
}

// ============================================================
// 🔎 فحص قائمة كاملة
// ============================================================

async function scanUniverse(symbols, exchange) {

    const results = [];

    /*
    لا يوجد حد MAX_SYMBOLS.
    لكن نعمل بالتتابع حتى لا نضرب EODHD
    بعشرات الطلبات في نفس اللحظة.
    */

    for (const item of symbols) {

        const symbol =
            typeof item === "string"
                ? item
                : item.Code || item.code;

        if (!symbol) {
            continue;
        }

        try {

            const result =
                await analyzeSymbol(
                    symbol,
                    exchange
                );

            if (result) {

                results.push(result);

                // نرسل الإشارة فور العثور عليها
                if (
                    result.signal !== "⚪ محايد"
                ) {
                    await notifySignal(result);
                }
            }

        } catch (err) {

            console.log(
                `⚠️ ${exchange} ${symbol}: ${err.message}`
            );
        }

        // تهدئة بسيطة للطلبات
        await sleep(150);
    }

    return results;
}

// ============================================================
// ⏳ تأخير
// ============================================================

function sleep(ms) {
    return new Promise(resolve =>
        setTimeout(resolve, ms)
    );
}

// ============================================================
// 🧠 منع تكرار الإشارات
// ============================================================

const sentSignals = new Map();

function signalKey(result) {

    return [
        result.exchange,
        result.symbol,
        result.signal
    ].join(":");
}

// ============================================================
// 📤 إرسال الإشارة
// ============================================================

async function notifySignal(result) {

    if (!CHAT_IDS.size) {
        console.log(
            "ℹ️ لا توجد محادثة Telegram مسجلة حتى الآن"
        );
        return;
    }

    const key = signalKey(result);

    const old = sentSignals.get(key);

    const now = Date.now();

    if (
        old &&
        now - old < SIGNAL_MEMORY_TIME
    ) {
        return;
    }

    sentSignals.set(key, now);

    const country =
        result.exchange === "TASI"
            ? "🇸🇦 تاسي"
            : result.exchange === "US"
                ? "🇺🇸 الأمريكي"
                : "🪙 العملات الرقمية";

    let text =

`🤖 AI PRO MAX 💀🚀

${country}

📊 الرمز: ${result.symbol}
💰 السعر: ${money(result.price)}

${result.signal}

🧠 الاتجاه:
${result.trend.direction}

💪 قوة الاتجاه:
${result.trend.strength}%

📏 ATR(14):
${money(result.atr)}

💧 السيولة:
${result.liquidity.strength}%

📊 حجم التداول:
${bigNumber(result.liquidity.volume)}

📍 الدعم:
${money(result.support)}

📍 المقاومة:
${money(result.resistance)}
`;

    if (result.targets.length) {

        text +=
`
🎯 أهداف ATR الديناميكية:

`;

        for (const target of result.targets) {

            if (result.trend.bullish) {

                text +=
`🟢 الهدف ${target.number}: ${money(target.price)}
`;

            } else if (result.trend.bearish) {

                text +=
`🔴✓ الهدف ${target.number}: ${money(target.price)}
`;
            }
        }
    }

    text +=
`
⏱ الفحص: تلقائي
🤖 AI PRO MAX
`;

    for (const chatId of CHAT_IDS) {

        try {

            await bot.sendMessage(
                chatId,
                text
            );

        } catch (err) {

            console.error(
                `❌ Telegram ${chatId}:`,
                err.message
            );
        }
    }
}

// ============================================================
// 📰 الأخبار عند الحاجة
// ============================================================

async function sendNews(symbol, exchange) {

    if (!CHAT_IDS.size) {
        return;
    }

    const news =
        await getNews(
            symbol,
            exchange
        );

    if (!news.length) {
        return;
    }

    let text =
`📰 أخبار ${symbol}

`;

    for (const item of news) {

        text +=
`• ${item.title}
المصدر: ${item.source}

`;
    }

    for (const chatId of CHAT_IDS) {

        try {

            await bot.sendMessage(
                chatId,
                text
            );

        } catch (err) {

            console.error(
                "❌ إرسال الأخبار:",
                err.message
            );
        }
    }
}

// ============================================================
// 🔄 دورة الفحص
// ============================================================

let scanning = false;

async function scanCycle() {

    if (scanning) {

        console.log(
            "⏳ توجد دورة فحص قيد التشغيل"
        );

        return;
    }

    scanning = true;

    console.log("");
    console.log(
        "🚀 AI PRO MAX — بدء دورة فحص جديدة"
    );
    console.log(
        new Date().toLocaleString("ar-SA")
    );

    let totalSignals = 0;

    try {

        // 🇸🇦
        try {

            const tasi =
                await scanTASI();

            totalSignals += tasi.length;

        } catch (err) {

            console.error(
                "❌ خطأ تاسي:",
                err.message
            );
        }

        // 🇺🇸
        try {

            const us =
                await scanUS();

            totalSignals += us.length;

        } catch (err) {

            console.error(
                "❌ خطأ الأمريكي:",
                err.message
            );
        }

        // 🪙
        try {

            const crypto =
                await scanCrypto();

            totalSignals += crypto.length;

        } catch (err) {

            console.error(
                "❌ خطأ العملات:",
                err.message
            );
        }

    } finally {

        console.log(
            `✅ نهاية الدورة — ${totalSignals} نتيجة`
        );

        scanning = false;
    }
}

// ============================================================
// ▶️ التشغيل
// ============================================================

setTimeout(() => {

    scanCycle();

}, 3000);

// ============================================================
// 🔄 الفحص التلقائي
// ============================================================

setInterval(() => {

    scanCycle();

}, SCAN_INTERVAL);

// ============================================================
// 🛡️ أخطاء عامة
// ============================================================

process.on("unhandledRejection", err => {

    console.error(
        "❌ unhandledRejection:",
        err
    );
});

process.on("uncaughtException", err => {

    console.error(
        "❌ uncaughtException:",
        err
    );
});

console.log(
    "⚡ التشغيل التلقائي: ON"
);

console.log(
    "⏱ دورة الفحص: كل 5 دقائق"
);