
"use strict";

/*
============================================================
🤖 AI PRO MAX — DUAL STOCK SCANNER
🇸🇦 TASI + 🇺🇸 US
EODHD ONLY + TELEGRAM
============================================================

مهم:
1) لا يوجد Bulk API
2) لا يوجد SR Exchange API
3) لا يوجد Yahoo
4) لا يوجد مواقع بيانات خارجية
5) المفتاح يوضع في Railway Environment Variables
============================================================
*/

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ ENV
// ============================================================

const PORT = Number(process.env.PORT || 3000);

const EODHD_API_KEY = process.env.EODHD_API_KEY;

const TASI_TOKEN = process.env.TASI_TOKEN;
const US_TOKEN = process.env.US_TOKEN;

const TASI_CHAT_ID = process.env.TASI_CHAT_ID;
const US_CHAT_ID = process.env.US_CHAT_ID;

// ============================================================
// ⚙️ إعدادات النظام
// ============================================================

const SCAN_INTERVAL_MS = 60 * 1000;

const US_MIN_PRICE = 0.20;

const SIGNAL_STRENGTH = 60;

const REQUEST_TIMEOUT = 20000;

const RETRY_COUNT = 2;

const BATCH_SIZE = 10;

// ============================================================
// 🌐 EXPRESS
// ============================================================

const app = express();

app.get("/", (req, res) => {
    res.status(200).send("AI PRO MAX Scanner is running");
});

app.get("/health", (req, res) => {
    res.status(200).json({
        status: "online",
        service: "AI PRO MAX",
        time: new Date().toISOString()
    });
});

app.listen(PORT, () => {
    console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// 🔐 فحص المتغيرات
// ============================================================

function checkEnvironment() {

    const missing = [];

    if (!EODHD_API_KEY) {
        missing.push("EODHD_API_KEY");
    }

    if (!TASI_TOKEN) {
        missing.push("TASI_TOKEN");
    }

    if (!US_TOKEN) {
        missing.push("US_TOKEN");
    }

    if (!TASI_CHAT_ID) {
        missing.push("TASI_CHAT_ID");
    }

    if (!US_CHAT_ID) {
        missing.push("US_CHAT_ID");
    }

    if (missing.length > 0) {

        console.error("");
        console.error("❌ متغيرات ناقصة:");
        console.error(missing.join(", "));
        console.error("");

        return false;
    }

    return true;
}

// ============================================================
// 🤖 TELEGRAM
// ============================================================

let tasiBot = null;
let usBot = null;

if (TASI_TOKEN) {
    tasiBot = new TelegramBot(TASI_TOKEN, {
        polling: true
    });
}

if (US_TOKEN) {
    usBot = new TelegramBot(US_TOKEN, {
        polling: true
    });
}

// ============================================================
// 🛡️ منع 409 من إيقاف البرنامج
// ============================================================

function setupTelegramErrors(bot, name) {

    if (!bot) {
        return;
    }

    bot.on("polling_error", (error) => {

        console.error(
            `❌ Telegram ${name} polling error:`,
            error.message || error
        );

    });

    bot.on("error", (error) => {

        console.error(
            `❌ Telegram ${name} error:`,
            error.message || error
        );

    });
}

setupTelegramErrors(tasiBot, "TASI");
setupTelegramErrors(usBot, "US");

// ============================================================
// 📡 HTTP REQUEST EODHD
// ============================================================

async function fetchJSON(url, attempt = 0) {

    const controller = new AbortController();

    const timer = setTimeout(() => {
        controller.abort();
    }, REQUEST_TIMEOUT);

    try {

        const response = await fetch(url, {
            method: "GET",
            headers: {
                "Accept": "application/json"
            },
            signal: controller.signal
        });

        const text = await response.text();

        if (!response.ok) {

            throw new Error(
                `HTTP ${response.status}: ${text.substring(0, 500)}`
            );
        }

        let data;

        try {

            data = JSON.parse(text);

        } catch {

            throw new Error(
                "EODHD returned invalid JSON"
            );
        }

        return data;

    } catch (error) {

        if (attempt < RETRY_COUNT) {

            await sleep(1000 * (attempt + 1));

            return fetchJSON(url, attempt + 1);
        }

        throw error;

    } finally {

        clearTimeout(timer);
    }
}

// ============================================================
// ⏱️ SLEEP
// ============================================================

function sleep(ms) {

    return new Promise(resolve => {
        setTimeout(resolve, ms);
    });
}

// ============================================================
// 🔗 EODHD URL
// ============================================================

function eodhd(path) {

    const separator = path.includes("?")
        ? "&"
        : "?";

    return `https://eodhd.com/api/${path}${separator}api_token=${encodeURIComponent(EODHD_API_KEY)}&fmt=json`;
}

// ============================================================
// 📋 الحصول على قائمة البورصات
// ============================================================

async function getExchanges() {

    const url = eodhd("exchanges-list/");

    return fetchJSON(url);
}

// ============================================================
// 🇺🇸 قائمة الأسهم الأمريكية
// ============================================================

async function getUSStocks() {

    /*
    EODHD يستخدم US كرمز موحد للسوق الأمريكي.
    */

    const url =
        eodhd(
            "exchange-symbol-list/US?type=common_stock"
        );

    const data = await fetchJSON(url);

    if (!Array.isArray(data)) {

        throw new Error(
            "قائمة الأسهم الأمريكية غير صالحة"
        );
    }

    return data
        .filter(stock => {

            if (!stock) {
                return false;
            }

            const code = String(
                stock.Code || ""
            ).trim();

            return code.length > 0;
        })
        .map(stock => {

            return {
                code: String(stock.Code).trim(),
                name: String(
                    stock.Name || stock.Code
                ).trim(),
                exchange: String(
                    stock.Exchange || "US"
                ).trim()
            };
        });
}

// ============================================================
// 🇸🇦 البحث عن رمز تداول سعودي صحيح
// ============================================================

async function findSaudiExchange() {

    const exchanges = await getExchanges();

    if (!Array.isArray(exchanges)) {

        throw new Error(
            "لم يتم استلام قائمة البورصات من EODHD"
        );
    }

    const candidates = exchanges.filter(exchange => {

        const text = JSON.stringify(exchange)
            .toLowerCase();

        return (
            text.includes("saudi") ||
            text.includes("tadawul")
        );
    });

    if (candidates.length === 0) {

        throw new Error(
            "لم يتم العثور على Tadawul في قائمة EODHD"
        );
    }

    console.log("");
    console.log("🇸🇦 بورصة السعودية الموجودة في EODHD:");

    for (const exchange of candidates) {

        console.log(
            JSON.stringify(exchange)
        );
    }

    /*
    نبحث أولاً عن Code الخاص بالبورصة.
    */

    for (const exchange of candidates) {

        const code =
            exchange.Code ||
            exchange.code;

        if (code) {
            return String(code).trim();
        }
    }

    throw new Error(
        "وجدنا Tadawul لكن لم نجد Exchange Code"
    );
}

// ============================================================
// 🇸🇦 قائمة أسهم تاسي
// ============================================================

async function getTASIStocks() {

    const exchangeCode =
        await findSaudiExchange();

    console.log(
        `🇸🇦 EODHD Saudi Exchange Code = ${exchangeCode}`
    );

    const url =
        eodhd(
            `exchange-symbol-list/${encodeURIComponent(exchangeCode)}?type=common_stock`
        );

    const data = await fetchJSON(url);

    if (!Array.isArray(data)) {

        throw new Error(
            "قائمة تاسي غير صالحة"
        );
    }

    const stocks =
        data
            .filter(stock => {

                if (!stock) {
                    return false;
                }

                const code =
                    String(
                        stock.Code || ""
                    ).trim();

                return code.length > 0;
            })
            .map(stock => {

                return {
                    code:
                        String(
                            stock.Code
                        ).trim(),

                    name:
                        String(
                            stock.Name ||
                            stock.Code
                        ).trim(),

                    exchange:
                        String(
                            stock.Exchange ||
                            exchangeCode
                        ).trim()
                };
            });

    return stocks;
}

// ============================================================
// 📊 جلب بيانات سهم
// ============================================================

async function getStockData(symbol) {

    /*
    EOD Historical API
    بدون Bulk
    */

    const url =
        eodhd(
            `eod/${encodeURIComponent(symbol)}?period=d&order=d&limit=60`
        );

    const data =
        await fetchJSON(url);

    if (!Array.isArray(data) || data.length === 0) {

        return null;
    }

    return data;
}

// ============================================================
// 📈 تحليل السهم
// ============================================================

function analyzeStock(stock, candles, market) {

    if (!candles || candles.length === 0) {
        return null;
    }

    const latest =
        candles[0];

    const previous =
        candles.length > 1
            ? candles[1]
            : null;

    const close =
        Number(
            latest.close
        );

    if (!Number.isFinite(close) || close <= 0) {
        return null;
    }

    const previousClose =
        previous
            ? Number(previous.close)
            : close;

    const open =
        Number(
            latest.open || close
        );

    const high =
        Number(
            latest.high || close
        );

    const low =
        Number(
            latest.low || close
        );

    const volume =
        Number(
            latest.volume || 0
        );

    let change = 0;

    if (
        Number.isFinite(previousClose) &&
        previousClose > 0
    ) {

        change =
            ((close - previousClose) /
                previousClose) *
            100;
    }

    // ========================================================
    // EMA
    // ========================================================

    const closes =
        candles
            .map(c => Number(c.close))
            .filter(Number.isFinite)
            .reverse();

    const ema7 =
        calculateEMA(closes, 7);

    const ema14 =
        calculateEMA(closes, 14);

    const ema25 =
        calculateEMA(closes, 25);

    const ema50 =
        calculateEMA(closes, 50);

    // ========================================================
    // الاتجاه
    // ========================================================

    let direction;

    if (change > 0) {

        direction = "صعود";

    } else if (change < 0) {

        direction = "هبوط";

    } else {

        direction = "محايد";
    }

    // ========================================================
    // قوة الاتجاه
    // ========================================================

    let strength =
        SIGNAL_STRENGTH;

    if (change >= 3) {

        strength += 20;

    } else if (change >= 1) {

        strength += 10;

    } else if (change <= -3) {

        strength += 20;

    } else if (change <= -1) {

        strength += 10;
    }

    strength =
        Math.min(
            100,
            strength
        );

    // ========================================================
    // الدعوم والمقاومات
    // ========================================================

    const recent =
        candles.slice(
            0,
            Math.min(
                candles.length,
                20
            )
        );

    const highs =
        recent
            .map(c => Number(c.high))
            .filter(Number.isFinite);

    const lows =
        recent
            .map(c => Number(c.low))
            .filter(Number.isFinite);

    const resistance =
        highs.length
            ? Math.max(...highs)
            : high;

    const support =
        lows.length
            ? Math.min(...lows)
            : low;

    // ========================================================
    // ATR
    // ========================================================

    const atr =
        calculateATR(
            candles,
            14
        );

    // ========================================================
    // الأهداف
    // ========================================================

    const targets =
        calculateTargets(
            close,
            atr,
            direction
        );

    // ========================================================
    // VWAP تقريبي من بيانات اليوميات
    // ========================================================

    const vwap =
        calculateVWAP(candles);

    return {

        symbol:
            stock.code,

        name:
            stock.name,

        market,

        price:
            close,

        previousClose,

        change,

        direction,

        strength,

        volume,

        open,

        high,

        low,

        ema7,

        ema14,

        ema25,

        ema50,

        vwap,

        support,

        resistance,

        atr,

        targets
    };
}

// ============================================================
// 📐 EMA
// ============================================================

function calculateEMA(values, period) {

    if (
        !Array.isArray(values) ||
        values.length === 0
    ) {

        return 0;
    }

    const multiplier =
        2 /
        (period + 1);

    let ema =
        values[0];

    for (
        let i = 1;
        i < values.length;
        i++
    ) {

        ema =
            (
                values[i] -
                ema
            ) *
            multiplier +
            ema;
    }

    return ema;
}

// ============================================================
// 📐 ATR
// ============================================================

function calculateATR(candles, period) {

    if (
        !Array.isArray(candles) ||
        candles.length < 2
    ) {

        return 0;
    }

    const trs = [];

    for (
        let i = 0;
        i < candles.length - 1;
        i++
    ) {

        const current =
            candles[i];

        const previous =
            candles[i + 1];

        const high =
            Number(current.high);

        const low =
            Number(current.low);

        const previousClose =
            Number(previous.close);

        if (
            !Number.isFinite(high) ||
            !Number.isFinite(low) ||
            !Number.isFinite(previousClose)
        ) {

            continue;
        }

        const tr =
            Math.max(
                high - low,
                Math.abs(
                    high -
                    previousClose
                ),
                Math.abs(
                    low -
                    previousClose
                )
            );

        trs.push(tr);
    }

    if (trs.length === 0) {
        return 0;
    }

    const usable =
        trs.slice(
            0,
            period
        );

    return (
        usable.reduce(
            (a, b) => a + b,
            0
        ) /
        usable.length
    );
}

// ============================================================
// 🎯 الأهداف
// ============================================================

function calculateTargets(
    price,
    atr,
    direction
) {

    const baseATR =
        atr > 0
            ? atr
            : price * 0.02;

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
        multiplier => {

            if (
                direction === "هبوط"
            ) {

                return Math.max(
                    0,
                    price -
                    (
                        baseATR *
                        multiplier
                    )
                );

            }

            return (
                price +
                (
                    baseATR *
                    multiplier
                )
            );
        }
    );
}

// ============================================================
// 📊 VWAP
// ============================================================

function calculateVWAP(candles) {

    let totalPV = 0;
    let totalVolume = 0;

    for (const candle of candles) {

        const high =
            Number(candle.high);

        const low =
            Number(candle.low);

        const close =
            Number(candle.close);

        const volume =
            Number(candle.volume);

        if (
            !Number.isFinite(high) ||
            !Number.isFinite(low) ||
            !Number.isFinite(close) ||
            !Number.isFinite(volume)
        ) {

            continue;
        }

        const typical =
            (
                high +
                low +
                close
            ) / 3;

        totalPV +=
            typical *
            volume;

        totalVolume +=
            volume;
    }

    if (totalVolume <= 0) {
        return 0;
    }

    return (
        totalPV /
        totalVolume
    );
}

// ============================================================
// 📨 تنسيق الإشارة
// ============================================================

function formatSignal(signal) {

    const emoji =
        signal.direction === "صعود"
            ? "🔥"
            : signal.direction === "هبوط"
                ? "🔻"
                : "⚪";

    const price =
        formatNumber(
            signal.price
        );

    const change =
        formatNumber(
            signal.change
        );

    const ema7 =
        formatNumber(
            signal.ema7
        );

    const ema14 =
        formatNumber(
            signal.ema14
        );

    const ema25 =
        formatNumber(
            signal.ema25
        );

    const ema50 =
        formatNumber(
            signal.ema50
        );

    const vwap =
        formatNumber(
            signal.vwap
        );

    const support =
        formatNumber(
            signal.support
        );

    const resistance =
        formatNumber(
            signal.resistance
        );

    const atr =
        formatNumber(
            signal.atr
        );

    const targets =
        signal.targets
            .map(
                (target, index) =>
                    `🎯 PT${index + 1}: ${formatNumber(target)}`
            )
            .join("\n");

    return (
        `${emoji} AI PRO MAX\n` +
        `━━━━━━━━━━━━━━━━━━\n` +
        `📊 ${signal.market}\n` +
        `🔹 ${signal.symbol}\n` +
        `🏢 ${signal.name}\n\n` +

        `💰 السعر: ${price}\n` +
        `📈 التغير: ${change}%\n` +
        `🚦 الإشارة: ${signal.direction}\n` +
        `💪 القوة: ${signal.strength}/100\n\n` +

        `📐 EMA 7: ${ema7}\n` +
        `📐 EMA 14: ${ema14}\n` +
        `📐 EMA 25: ${ema25}\n` +
        `📐 EMA 50: ${ema50}\n` +
        `📊 VWAP: ${vwap}\n\n` +

        `🟢 الدعم: ${support}\n` +
        `🔴 المقاومة: ${resistance}\n` +
        `📏 ATR: ${atr}\n` +
        `📦 الحجم: ${formatVolume(signal.volume)}\n\n` +

        `${targets}\n` +

        `━━━━━━━━━━━━━━━━━━\n` +
        `🤖 AI PRO MAX`
    );
}

// ============================================================
// 🔢 تنسيق الأرقام
// ============================================================

function formatNumber(value) {

    if (!Number.isFinite(Number(value))) {
        return "0";
    }

    return Number(value)
        .toFixed(4)
        .replace(/\.?0+$/, "");
}

// ============================================================
// 📦 تنسيق الحجم
// ============================================================

function formatVolume(value) {

    const n =
        Number(value);

    if (!Number.isFinite(n)) {
        return "0";
    }

    if (n >= 1000000000) {

        return (
            (n / 1000000000)
                .toFixed(2) +
            "B"
        );
    }

    if (n >= 1000000) {

        return (
            (n / 1000000)
                .toFixed(2) +
            "M"
        );
    }

    if (n >= 1000) {

        return (
            (n / 1000)
                .toFixed(2) +
            "K"
        );
    }

    return String(n);
}

// ============================================================
// 📤 إرسال Telegram
// ============================================================

async function sendTelegram(
    bot,
    chatId,
    text
) {

    if (!bot || !chatId) {
        return;
    }

    try {

        await bot.sendMessage(
            chatId,
            text,
            {
                disable_web_page_preview: true
            }
        );

    } catch (error) {

        console.error(
            "❌ Telegram send error:",
            error.message || error
        );
    }
}

// ============================================================
// 🔍 فحص سهم
// ============================================================

async function scanSingleStock(
    stock,
    market
) {

    try {

        const symbol =
            market === "🇺🇸 السوق الأمريكي"
                ? `${stock.code}.${stock.exchange || "US"}`
                : `${stock.code}.${stock.exchange}`;

        const candles =
            await getStockData(symbol);

        if (!candles) {
            return null;
        }

        const result =
            analyzeStock(
                stock,
                candles,
                market
            );

        if (!result) {
            return null;
        }

        if (
            market === "🇺🇸 السوق الأمريكي" &&
            result.price < US_MIN_PRICE
        ) {

            return null;
        }

        return result;

    } catch (error) {

        console.error(
            `❌ ${market} ${stock.code}:`,
            error.message || error
        );

        return null;
    }
}

// ============================================================
// 🔄 فحص مجموعة
// ============================================================

async function scanStocks(
    stocks,
    market,
    bot,
    chatId
) {

    let sent = 0;
    let scanned = 0;

    for (
        let i = 0;
        i < stocks.length;
        i += BATCH_SIZE
    ) {

        const batch =
            stocks.slice(
                i,
                i + BATCH_SIZE
            );

        const results =
            await Promise.all(
                batch.map(stock =>
                    scanSingleStock(
                        stock,
                        market
                    )
                )
            );

        for (const result of results) {

            if (!result) {
                continue;
            }

            scanned++;

            /*
            لا يوجد شرط قوة يمنع الإرسال.
            */

            const message =
                formatSignal(result);

            await sendTelegram(
                bot,
                chatId,
                message
            );

            sent++;

            await sleep(1000);
        }
    }

    return {
        scanned,
        sent
    };
}

// ============================================================
// 🇺🇸 فحص السوق الأمريكي
// ============================================================

let usRunning = false;

async function scanUS() {

    if (usRunning) {

        console.log(
            "⏳ فحص US السابق ما زال يعمل"
        );

        return;
    }

    usRunning = true;

    console.log("");
    console.log(
        "🇺🇸 بدء فحص السوق الأمريكي..."
    );

    try {

        const stocks =
            await getUSStocks();

        console.log(
            `🇺🇸 عدد الأسهم المحملة: ${stocks.length}`
        );

        const result =
            await scanStocks(
                stocks,
                "🇺🇸 السوق الأمريكي",
                usBot,
                US_CHAT_ID
            );

        console.log(
            `🇺🇸 انتهى الفحص | تمت معالجة: ${result.scanned} | إرسال: ${result.sent}`
        );

    } catch (error) {

        console.error(
            "❌ US error:",
            error.message || error
        );

        await sendTelegram(
            usBot,
            US_CHAT_ID,
            `❌ خطأ السوق الأمريكي\n\n${error.message || error}`
        );
    }

    usRunning = false;
}

// ============================================================
// 🇸🇦 فحص تاسي
// ============================================================

let tasiRunning = false;

async function scanTASI() {

    if (tasiRunning) {

        console.log(
            "⏳ فحص TASI السابق ما زال يعمل"
        );

        return;
    }

    tasiRunning = true;

    console.log("");
    console.log(
        "🇸🇦 بدء فحص تاسي..."
    );

    try {

        const stocks =
            await getTASIStocks();

        console.log(
            `🇸🇦 عدد الأسهم المحملة: ${stocks.length}`
        );

        const result =
            await scanStocks(
                stocks,
                "🇸🇦 السوق السعودي",
                tasiBot,
                TASI_CHAT_ID
            );

        console.log(
            `🇸🇦 انتهى الفحص | تمت معالجة: ${result.scanned} | إرسال: ${result.sent}`
        );

    } catch (error) {

        console.error(
            "❌ TASI error:",
            error.message || error
        );

        await sendTelegram(
            tasiBot,
            TASI_CHAT_ID,
            `❌ خطأ السوق السعودي\n\n${error.message || error}`
        );
    }

    tasiRunning = false;
}

// ============================================================
// 🟢 أوامر TELEGRAM
// ============================================================

if (tasiBot) {

    tasiBot.onText(
        /^\/start$/i,
        async msg => {

            await tasiBot.sendMessage(
                msg.chat.id,
                "🇸🇦 AI PRO MAX\nتم تشغيل بوت السوق السعودي."
            );
        }
    );

    tasiBot.onText(
        /^\/scan$/i,
        async msg => {

            await tasiBot.sendMessage(
                msg.chat.id,
                "🔍 بدء فحص تاسي الآن..."
            );

            scanTASI();
        }
    );
}

if (usBot) {

    usBot.onText(
        /^\/start$/i,
        async msg => {

            await usBot.sendMessage(
                msg.chat.id,
                "🇺🇸 AI PRO MAX\nتم تشغيل بوت السوق الأمريكي."
            );
        }
    );

    usBot.onText(
        /^\/scan$/i,
        async msg => {

            await usBot.sendMessage(
                msg.chat.id,
                "🔍 بدء فحص السوق الأمريكي الآن..."
            );

            scanUS();
        }
    );
}

// ============================================================
// 🔁 التشغيل التلقائي
// ============================================================

let automaticStarted = false;

function startAutomaticScanner() {

    if (automaticStarted) {
        return;
    }

    automaticStarted = true;

    console.log("");
    console.log(
        "🚀 AI PRO MAX — التشغيل التلقائي"
    );

    /*
    أول فحص
    */

    setTimeout(() => {

        scanTASI();

    }, 5000);

    setTimeout(() => {

        scanUS();

    }, 10000);

    /*
    تاسي كل دقيقة
    */

    setInterval(() => {

        scanTASI();

    }, SCAN_INTERVAL_MS);

    /*
    الأمريكي كل دقيقة
    */

    setInterval(() => {

        scanUS();

    }, SCAN_INTERVAL_MS);
}

// ============================================================
// 🟢 START
// ============================================================

if (checkEnvironment()) {

    console.log("");
    console.log(
        "========================================"
    );

    console.log(
        "🤖 AI PRO MAX"
    );

    console.log(
        "🇸🇦 TASI: جاهز"
    );

    console.log(
        "🇺🇸 US: جاهز"
    );

    console.log(
        "📡 EODHD: متصل من خلال المفتاح"
    );

    console.log(
        "⏱️ الفحص: كل 60 ثانية"
    );

    console.log(
        "========================================"
    );

    startAutomaticScanner();

} else {

    console.error(
        "❌ لم يبدأ البوت بسبب نقص Environment Variables"
    );
}