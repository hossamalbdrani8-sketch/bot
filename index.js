
"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// 🤖 AI PRO MAX 💀🚀
// 🇸🇦 TASI + 🇺🇸 US/NASDAQ + 🪙 CRYPTO
// ============================================================

// ------------------------------------------------------------
// 🔐 قراءة Telegram من التكوينات الموجودة
// ------------------------------------------------------------
const TELEGRAM_TOKEN =
    process.env.TELEGRAM_TOKEN ||
    process.env.TELEGRAM_BOT_TOKEN ||
    process.env.BOT_TOKEN ||
    "";

const TELEGRAM_CHAT_ID =
    process.env.TELEGRAM_CHAT_ID ||
    process.env.CHAT_ID ||
    "";

// ------------------------------------------------------------
// 🔑 EODHD
// ------------------------------------------------------------
const EODHD_TOKEN =
    process.env.EODHD_TOKEN ||
    process.env.EODHD_API_KEY ||
    process.env.EODHD_API_TOKEN ||
    process.env.API_TOKEN ||
    "";

// ------------------------------------------------------------
// 🇸🇦 تاسي
// ------------------------------------------------------------
const TASI_CONFIG =
    process.env.TASI_CONFIG ||
    process.env.TASI_API ||
    process.env.TASI_TOKEN ||
    "";

// ------------------------------------------------------------
// 🇺🇸 الأمريكي
// ------------------------------------------------------------
const US_CONFIG =
    process.env.US_CONFIG ||
    process.env.US_API ||
    process.env.US_TOKEN ||
    "";

// ------------------------------------------------------------
// 🪙 العملات الرقمية
// ------------------------------------------------------------
const CRYPTO_CONFIG =
    process.env.CRYPTO_CONFIG ||
    process.env.CRYPTO_API ||
    process.env.CRYPTO_TOKEN ||
    "";

// ------------------------------------------------------------
// 🌐 PORT
// ------------------------------------------------------------
const PORT = Number(process.env.PORT || 3000);

// ------------------------------------------------------------
// ⚙️ إعدادات التشغيل
// ------------------------------------------------------------
const SCAN_INTERVAL = 5 * 60 * 1000;

const MIN_US_PRICE = 0.20;

let bot = null;

let subscribers = new Set();

let running = false;

let lastScan = {
    tasi: 0,
    us: 0,
    crypto: 0
};

// ============================================================
// 🛑 فحص Telegram
// ============================================================

if (!TELEGRAM_TOKEN) {
    console.error("❌ TELEGRAM_TOKEN غير موجود");
    console.error(
        "المتغيرات المقبولة: TELEGRAM_TOKEN أو TELEGRAM_BOT_TOKEN أو BOT_TOKEN"
    );
} else {
    try {
        bot = new TelegramBot(TELEGRAM_TOKEN, {
            polling: true
        });

        console.log("✅ Telegram Bot يعمل");

    } catch (error) {
        console.error("❌ خطأ تشغيل Telegram:", error.message);
    }
}

// ============================================================
// 🔑 فحص EODHD
// ============================================================

if (!EODHD_TOKEN) {
    console.error("❌ EODHD_TOKEN غير موجود");
} else {
    console.log("✅ EODHD Token موجود");
}

// ============================================================
// 📱 تسجيل المستخدم
// ============================================================

if (bot) {

    bot.onText(/^\/start$/, async (msg) => {

        const chatId = String(msg.chat.id);

        subscribers.add(chatId);

        console.log(`✅ تمت إضافة Telegram Chat: ${chatId}`);

        await bot.sendMessage(
            chatId,
            [
                "🤖 AI PRO MAX 💀🚀",
                "",
                "✅ البوت يعمل الآن",
                "",
                "🇸🇦 تاسي: يعمل",
                "🇺🇸 الأمريكي: يعمل",
                "🪙 العملات الرقمية: يعمل",
                "",
                "⚡ الفحص تلقائي",
                "⏱️ التحديث كل 5 دقائق",
                "",
                "لا تحتاج إلى تشغيل الفحص يدويًا."
            ].join("\n")
        );
    });

    bot.on("polling_error", (error) => {
        console.error("❌ Telegram Polling:", error.message);
    });
}

// ============================================================
// 🌐 EODHD Request
// ============================================================

async function eodhd(path) {

    if (!EODHD_TOKEN) {
        throw new Error("EODHD_TOKEN غير موجود");
    }

    const separator = path.includes("?") ? "&" : "?";

    const url =
        "https://eodhd.com/api" +
        path +
        separator +
        "api_token=" +
        encodeURIComponent(EODHD_TOKEN) +
        "&fmt=json";

    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(
            `EODHD HTTP ${response.status}`
        );
    }

    return await response.json();
}

// ============================================================
// 📊 حساب EMA
// ============================================================

function ema(values, period) {

    if (!values || values.length < period) {
        return null;
    }

    const multiplier = 2 / (period + 1);

    let result = 0;

    for (let i = 0; i < period; i++) {
        result += Number(values[i]) || 0;
    }

    result /= period;

    for (let i = period; i < values.length; i++) {

        const value = Number(values[i]) || 0;

        result =
            (value - result) * multiplier +
            result;
    }

    return result;
}

// ============================================================
// 📈 ATR
// ============================================================

function calculateATR(candles, period = 14) {

    if (!candles || candles.length < period + 1) {
        return null;
    }

    const tr = [];

    for (let i = 1; i < candles.length; i++) {

        const high = Number(candles[i].high);
        const low = Number(candles[i].low);
        const previousClose =
            Number(candles[i - 1].close);

        if (
            !Number.isFinite(high) ||
            !Number.isFinite(low) ||
            !Number.isFinite(previousClose)
        ) {
            continue;
        }

        const range1 = high - low;
        const range2 = Math.abs(high - previousClose);
        const range3 = Math.abs(low - previousClose);

        tr.push(
            Math.max(
                range1,
                range2,
                range3
            )
        );
    }

    if (tr.length < period) {
        return null;
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
// 🎯 أهداف ATR — 8 أهداف
// ============================================================

function calculateTargets(price, atr) {

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

        return {
            name: `TP${index + 1}`,
            price: price + atr * m,
            distance: atr * m
        };
    });
}

// ============================================================
// 📊 الدعم والمقاومة
// ============================================================

function supportResistance(candles, lookback = 30) {

    if (!candles || candles.length < 5) {
        return {
            support: null,
            resistance: null
        };
    }

    const data =
        candles.slice(-lookback);

    const lows = data
        .map(x => Number(x.low))
        .filter(Number.isFinite);

    const highs = data
        .map(x => Number(x.high))
        .filter(Number.isFinite);

    if (!lows.length || !highs.length) {
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
// 💧 قوة السيولة
// ============================================================

function liquidityStrength(candles) {

    if (!candles || candles.length < 10) {
        return 0;
    }

    const volumes = candles
        .map(x => Number(x.volume))
        .filter(Number.isFinite);

    if (volumes.length < 5) {
        return 0;
    }

    const latest =
        volumes[volumes.length - 1];

    const previous =
        volumes.slice(-10, -1);

    const average =
        previous.reduce(
            (a, b) => a + b,
            0
        ) / previous.length;

    if (!average) {
        return 0;
    }

    return latest / average;
}

// ============================================================
// 🧠 تحليل السهم
// ============================================================

function analyze(symbol, candles, market) {

    if (!candles || candles.length < 20) {
        return null;
    }

    const closes = candles
        .map(x => Number(x.close))
        .filter(Number.isFinite);

    const highs = candles
        .map(x => Number(x.high))
        .filter(Number.isFinite);

    const lows = candles
        .map(x => Number(x.low))
        .filter(Number.isFinite);

    const price =
        closes[closes.length - 1];

    if (!Number.isFinite(price)) {
        return null;
    }

    const emaFast =
        ema(closes, 10);

    const ema50 =
        ema(closes, 50);

    const ema200 =
        ema(closes, 200);

    const atr =
        calculateATR(candles, 14);

    const sr =
        supportResistance(candles);

    const liquidity =
        liquidityStrength(candles);

    let signal = "محايد";

    if (
        emaFast &&
        ema50 &&
        price > emaFast &&
        emaFast > ema50
    ) {
        signal = "شراء قوي";
    }

    else if (
        emaFast &&
        price > emaFast
    ) {
        signal = "شراء";
    }

    else if (
        emaFast &&
        price < emaFast
    ) {
        signal = "مراقبة";
    }

    const targets =
        calculateTargets(
            price,
            atr
        );

    return {
        symbol,
        market,
        price,
        signal,
        emaFast,
        ema50,
        ema200,
        atr,
        support: sr.support,
        resistance: sr.resistance,
        liquidity,
        targets
    };
}

// ============================================================
// 📡 جلب الشموع
// ============================================================

async function getIntraday(symbol) {

    return await eodhd(
        `/intraday/${encodeURIComponent(symbol)}?interval=5m`
    );
}

// ============================================================
// 🇸🇦 تاسي
// ============================================================

async function scanTASI() {

    console.log("🇸🇦 بدء فحص تاسي...");

    lastScan.tasi =
        Date.now();

    const list =
        await eodhd(
            "/exchange-symbol-list/TADAWUL"
        );

    if (!Array.isArray(list)) {
        console.log("⚠️ لم يتم استلام قائمة تاسي");
        return [];
    }

    const results = [];

    for (const item of list) {

        const code =
            item.Code ||
            item.code ||
            item.Symbol ||
            item.symbol;

        if (!code) continue;

        try {

            const ticker =
                code.includes(".")
                    ? code
                    : `${code}.SR`;

            const candles =
                await getIntraday(ticker);

            const analysis =
                analyze(
                    ticker,
                    candles,
                    "TASI"
                );

            if (
                analysis &&
                (
                    analysis.signal === "شراء قوي" ||
                    analysis.signal === "شراء"
                )
            ) {
                results.push(analysis);
            }

        } catch (error) {

            console.log(
                `⚠️ TASI ${code}: ${error.message}`
            );
        }
    }

    console.log(
        `🇸🇦 تاسي: ${results.length} إشارات`
    );

    return results;
}

// ============================================================
// 🇺🇸 US / NASDAQ
// ============================================================

async function scanUS() {

    console.log("🇺🇸 بدء فحص الأمريكي...");

    lastScan.us =
        Date.now();

    const list =
        await eodhd(
            "/exchange-symbol-list/US"
        );

    if (!Array.isArray(list)) {
        console.log("⚠️ لم يتم استلام قائمة الأمريكي");
        return [];
    }

    const results = [];

    for (const item of list) {

        const code =
            item.Code ||
            item.code ||
            item.Symbol ||
            item.symbol;

        if (!code) continue;

        try {

            const ticker =
                code.includes(".")
                    ? code
                    : `${code}.US`;

            const real =
                await eodhd(
                    `/real-time/${encodeURIComponent(ticker)}`
                );

            const price =
                Number(
                    real.close ||
                    real.price ||
                    real.close_price
                );

            if (
                !Number.isFinite(price) ||
                price < MIN_US_PRICE
            ) {
                continue;
            }

            const candles =
                await getIntraday(ticker);

            const analysis =
                analyze(
                    ticker,
                    candles,
                    "US"
                );

            if (
                analysis &&
                (
                    analysis.signal === "شراء قوي" ||
                    analysis.signal === "شراء"
                )
            ) {
                results.push(analysis);
            }

        } catch (error) {

            console.log(
                `⚠️ US ${code}: ${error.message}`
            );
        }
    }

    console.log(
        `🇺🇸 الأمريكي: ${results.length} إشارات`
    );

    return results;
}

// ============================================================
// 🪙 العملات الرقمية
// ============================================================

async function scanCrypto() {

    console.log("🪙 بدء فحص العملات الرقمية...");

    lastScan.crypto =
        Date.now();

    const list =
        await eodhd(
            "/exchange-symbol-list/CC"
        );

    if (!Array.isArray(list)) {
        console.log("⚠️ لم يتم استلام قائمة العملات");
        return [];
    }

    const results = [];

    for (const item of list) {

        const code =
            item.Code ||
            item.code ||
            item.Symbol ||
            item.symbol;

        if (!code) continue;

        try {

            const ticker =
                code.includes(".")
                    ? code
                    : `${code}.CC`;

            const candles =
                await getIntraday(ticker);

            const analysis =
                analyze(
                    ticker,
                    candles,
                    "CRYPTO"
                );

            if (
                analysis &&
                (
                    analysis.signal === "شراء قوي" ||
                    analysis.signal === "شراء"
                )
            ) {
                results.push(analysis);
            }

        } catch (error) {

            console.log(
                `⚠️ CRYPTO ${code}: ${error.message}`
            );
        }
    }

    console.log(
        `🪙 العملات: ${results.length} إشارات`
    );

    return results;
}

// ============================================================
// 📩 رسالة الإشارة
// ============================================================

function formatSignal(x) {

    let text = "";

    text += "🤖 AI PRO MAX 💀🚀\n";
    text += "━━━━━━━━━━━━━━━━━━\n";

    text +=
        `📊 السوق: ${x.market}\n`;

    text +=
        `🔹 الرمز: ${x.symbol}\n`;

    text +=
        `💰 السعر: ${x.price.toFixed(4)}\n`;

    text +=
        `🚦 الإشارة: ${x.signal}\n`;

    if (x.emaFast) {
        text +=
            `📈 EMA10: ${x.emaFast.toFixed(4)}\n`;
    }

    if (x.ema50) {
        text +=
            `📈 EMA50: ${x.ema50.toFixed(4)}\n`;
    }

    if (x.ema200) {
        text +=
            `📈 EMA200: ${x.ema200.toFixed(4)}\n`;
    }

    if (x.atr) {
        text +=
            `📏 ATR14: ${x.atr.toFixed(4)}\n`;
    }

    if (x.support) {
        text +=
            `🟢 الدعم: ${x.support.toFixed(4)}\n`;
    }

    if (x.resistance) {
        text +=
            `🔴 المقاومة: ${x.resistance.toFixed(4)}\n`;
    }

    if (x.liquidity) {

        text +=
            `💧 قوة السيولة: ${x.liquidity.toFixed(2)}x\n`;
    }

    if (x.targets.length) {

        text += "\n🎯 أهداف ATR:\n";

        for (const target of x.targets) {

            text +=
                `${target.name}: ${target.price.toFixed(4)}\n`;
        }
    }

    text +=
        "\n━━━━━━━━━━━━━━━━━━\n";

    text +=
        "⚡ فحص تلقائي AI PRO MAX";

    return text;
}

// ============================================================
// 📤 إرسال النتائج
// ============================================================

async function sendResults(results) {

    if (!bot) {
        return;
    }

    const ids =
        new Set(subscribers);

    if (TELEGRAM_CHAT_ID) {
        ids.add(
            String(TELEGRAM_CHAT_ID)
        );
    }

    if (!ids.size) {

        console.log(
            "ℹ️ لا يوجد Telegram Chat مسجل حتى الآن"
        );

        return;
    }

    // إرسال أفضل 20 إشارة فقط في كل دورة
    const selected =
        results
            .sort(
                (a, b) =>
                    b.liquidity - a.liquidity
            )
            .slice(0, 20);

    for (const item of selected) {

        const message =
            formatSignal(item);

        for (const chatId of ids) {

            try {

                await bot.sendMessage(
                    chatId,
                    message
                );

            } catch (error) {

                console.error(
                    "❌ إرسال Telegram:",
                    error.message
                );
            }
        }
    }
}

// ============================================================
// 🚀 دورة الفحص الكاملة
// ============================================================

async function fullScan() {

    if (running) {

        console.log(
            "⏳ يوجد فحص يعمل حاليًا"
        );

        return;
    }

    running = true;

    console.log(
        "\n🚀 AI PRO MAX — بدء دورة فحص جديدة"
    );

    try {

        const allResults = [];

        // 🇸🇦
        try {

            const tasi =
                await scanTASI();

            allResults.push(
                ...tasi
            );

        } catch (error) {

            console.error(
                "❌ خطأ تاسي:",
                error.message
            );
        }

        // 🇺🇸
        try {

            const us =
                await scanUS();

            allResults.push(
                ...us
            );

        } catch (error) {

            console.error(
                "❌ خطأ الأمريكي:",
                error.message
            );
        }

        // 🪙
        try {

            const crypto =
                await scanCrypto();

            allResults.push(
                ...crypto
            );

        } catch (error) {

            console.error(
                "❌ خطأ العملات:",
                error.message
            );
        }

        console.log(
            `✅ نهاية الدورة — ${allResults.length} إشارة`
        );

        await sendResults(
            allResults
        );

    } catch (error) {

        console.error(
            "❌ خطأ دورة الفحص:",
            error.message
        );

    } finally {

        running = false;
    }
}

// ============================================================
// 🌐 Railway Health Server
// ============================================================

const app =
    express();

app.get("/", (req, res) => {

    res.json({
        bot: "AI PRO MAX 💀🚀",
        status: "online",
        telegram: !!bot,
        eodhd: !!EODHD_TOKEN,
        markets: {
            tasi: !!TASI_CONFIG || !!EODHD_TOKEN,
            us: !!US_CONFIG || !!EODHD_TOKEN,
            crypto: !!CRYPTO_CONFIG || !!EODHD_TOKEN
        },
        automatic: true,
        intervalMinutes: 5,
        lastScan
    });
});

app.get("/health", (req, res) => {

    res.status(200).send("AI PRO MAX ONLINE");
});

app.listen(
    PORT,
    () => {

        console.log(
            `🌐 Server running on port ${PORT}`
        );

        console.log(
            "🇸🇦 TASI: جاهز"
        );

        console.log(
            "🇺🇸 US: جاهز"
        );

        console.log(
            "🪙 CRYPTO: جاهز"
        );

        console.log(
            "⚡ التشغيل التلقائي: ON"
        );

        // أول فحص
        setTimeout(
            fullScan,
            10000
        );

        // فحص تلقائي كل 5 دقائق
        setInterval(
            fullScan,
            SCAN_INTERVAL
        );
    }
);