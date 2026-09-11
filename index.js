
"use strict";
/*
============================================================
💀🚀 AI PRO MAX — AUTONOMOUS TELEGRAM SCANNER
============================================================
🇸🇦 TASI
🇺🇸 US / NASDAQ
🪙 CRYPTO
📰 EODHD NEWS
🧠 AI PRO MAX TREND
📏 ATR(14)
🎯 8 ATR TARGETS
📍 SUPPORT / RESISTANCE
💧 LIQUIDITY
🤖 AUTOMATIC / 24-7
IMPORTANT:
All tokens/API keys are read from environment variables.
No keys are stored in this file.
============================================================
*/
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
// ============================================================
// ENVIRONMENT VARIABLES
// ============================================================
function env(...names) {
    for (const name of names) {
        if (
            process.env[name] !== undefined &&
            process.env[name] !== ""
        ) {
            return process.env[name];
        }
    }
    return "";
}
const TELEGRAM_TOKEN = env(
    "TELEGRAM_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "BOT_TOKEN"
);
const EODHD_API_KEY = env(
    "EODHD_API_KEY",
    "EODHD_TOKEN",
    "EODHD_API_TOKEN",
    "API_TOKEN"
);
const TASI_CONFIG = env(
    "TASI_CONFIG",
    "TASI_API",
    "TASI_TOKEN"
);
const US_CONFIG = env(
    "US_CONFIG",
    "US_API",
    "US_TOKEN"
);
const CRYPTO_CONFIG = env(
    "CRYPTO_CONFIG",
    "CRYPTO_API",
    "CRYPTO_TOKEN"
);
const PORT = Number(
    env("PORT") || 3000
);
const US_MIN_PRICE = 0.20;
const SCAN_INTERVAL =
    5 * 60 * 1000;
const ATR_PERIOD = 14;
const MIN_BARS = 30;
// ============================================================
// VALIDATION
// ============================================================
if (!TELEGRAM_TOKEN) {
    console.error(
        "❌ TELEGRAM_TOKEN غير موجود في Variables"
    );
    process.exit(1);
}
if (!EODHD_API_KEY) {
    console.error(
        "❌ EODHD API Token غير موجود في Variables"
    );
    process.exit(1);
}
// ============================================================
// TELEGRAM
// ============================================================
const bot = new TelegramBot(
    TELEGRAM_TOKEN,
    {
        polling: true
    }
);
// ============================================================
// EXPRESS
// ============================================================
const app = express();
app.get("/", (req, res) => {
    res.status(200).send(
        "💀🚀 AI PRO MAX يعمل"
    );
});
app.get("/health", (req, res) => {
    res.json({
        status: "online",
        bot: "AI PRO MAX",
        tasi: true,
        us: true,
        crypto: true,
        eodhd: true,
        automatic: true,
        time: new Date().toISOString()
    });
});
app.listen(PORT, () => {
    console.log(
        `🌐 Web server running on ${PORT}`
    );
});
// ============================================================
// STATE
// ============================================================
const state = {
    chats: new Set(),
    running: false,
    lastScan: {
        tasi: null,
        us: null,
        crypto: null
    },
    sentSignals: new Map(),
    exchanges: {
        tasi: "TADAWUL",
        us: "US",
        crypto: "CC"
    },
    universe: {
        tasi: [],
        us: [],
        crypto: []
    }
};
// ============================================================
// HELPERS
// ============================================================
function sleep(ms) {
    return new Promise(
        resolve => setTimeout(resolve, ms)
    );
}
function num(value, fallback = 0) {
    const n = Number(value);
    return Number.isFinite(n)
        ? n
        : fallback;
}
function priceFormat(value) {
    const n = num(value);
    if (n >= 1000)
        return n.toFixed(2);
    if (n >= 1)
        return n.toFixed(3);
    return n.toFixed(4);
}
function pct(value) {
    return `${num(value).toFixed(2)}%`;
}
// ============================================================
// EODHD REQUEST
// ============================================================
async function eodhd(
    endpoint,
    params = {}
) {
    const url =
        new URL(
            `https://eodhd.com${endpoint}`
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
        if (
            value !== undefined &&
            value !== null &&
            value !== ""
        ) {
            url.searchParams.set(
                key,
                String(value)
            );
        }
    }
    const response =
        await fetch(
            url,
            {
                method: "GET",
                headers: {
                    "Accept":
                        "application/json",
                    "User-Agent":
                        "AI-PRO-MAX"
                }
            }
        );
    const text =
        await response.text();
    if (!response.ok) {
        throw new Error(
            `EODHD ${response.status}`
        );
    }
    try {
        return JSON.parse(text);
    } catch {
        throw new Error(
            "EODHD JSON error"
        );
    }
}
// ============================================================
// ATR
// ============================================================
function ATR(
    bars,
    period = 14
) {
    if (
        bars.length <
        period + 1
    ) {
        return 0;
    }
    const trs = [];
    for (
        let i = 1;
        i < bars.length;
        i++
    ) {
        const high =
            num(bars[i].high);
        const low =
            num(bars[i].low);
        const previous =
            num(
                bars[i - 1].close
            );
        const tr =
            Math.max(
                high - low,
                Math.abs(
                    high - previous
                ),
                Math.abs(
                    low - previous
                )
            );
        trs.push(tr);
    }
    const recent =
        trs.slice(-period);
    return recent.reduce(
        (a, b) => a + b,
        0
    ) / recent.length;
}
// ============================================================
// EMA
// ============================================================
function EMA(
    values,
    period
) {
    if (!values.length)
        return 0;
    const multiplier =
        2 / (period + 1);
    let ema =
        values[0];
    for (
        let i = 1;
        i < values.length;
        i++
    ) {
        ema =
            (
                values[i] *
                multiplier
            ) +
            (
                ema *
                (1 - multiplier)
            );
    }
    return ema;
}
// ============================================================
// RSI
// ============================================================
function RSI(
    values,
    period = 14
) {
    if (
        values.length <= period
    ) {
        return 50;
    }
    let gain = 0;
    let loss = 0;
    for (
        let i = 1;
        i <= period;
        i++
    ) {
        const change =
            values[i] -
            values[i - 1];
        if (change >= 0)
            gain += change;
        else
            loss += Math.abs(change);
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
        const change =
            values[i] -
            values[i - 1];
        const currentGain =
            change > 0
                ? change
                : 0;
        const currentLoss =
            change < 0
                ? Math.abs(change)
                : 0;
        avgGain =
            (
                avgGain *
                (period - 1) +
                currentGain
            ) / period;
        avgLoss =
            (
                avgLoss *
                (period - 1) +
                currentLoss
            ) / period;
    }
    if (avgLoss === 0)
        return 100;
    const rs =
        avgGain / avgLoss;
    return (
        100 -
        100 / (1 + rs)
    );
}
// ============================================================
// LIQUIDITY
// ============================================================
function liquidity(
    bars
) {
    if (
        bars.length < 20
    ) {
        return {
            ratio: 1,
            label: "عادية 🟡"
        };
    }
    const recent =
        bars.slice(-5);
    const previous =
        bars.slice(-20, -5);
    const recentVolume =
        recent.reduce(
            (sum, bar) =>
                sum +
                num(bar.volume),
            0
        ) /
        recent.length;
    const previousVolume =
        previous.reduce(
            (sum, bar) =>
                sum +
                num(bar.volume),
            0
        ) /
        previous.length;
    const ratio =
        previousVolume > 0
            ? recentVolume /
              previousVolume
            : 1;
    let label =
        "عادية 🟡";
    if (ratio >= 2.5)
        label =
            "قوية جدًا 🟢";
    else if (ratio >= 1.5)
        label =
            "قوية 🟢";
    else if (ratio <= 0.65)
        label =
            "ضعيفة 🔴";
    return {
        ratio,
        label
    };
}
// ============================================================
// SUPPORT / RESISTANCE
// ============================================================
function levels(
    bars
) {
    const recent =
        bars.slice(-30);
    if (!recent.length) {
        return {
            support: 0,
            resistance: 0
        };
    }
    const lows =
        recent.map(
            x => num(x.low)
        );
    const highs =
        recent.map(
            x => num(x.high)
        );
    return {
        support:
            Math.min(...lows),
        resistance:
            Math.max(...highs)
    };
}
// ============================================================
// AI PRO MAX
// ============================================================
function AI_PRO_MAX(
    bars
) {
    const closes =
        bars
            .map(
                x => num(x.close)
            )
            .filter(
                x => x > 0
            );
    if (
        closes.length <
        MIN_BARS
    ) {
        return null;
    }
    const price =
        closes[
            closes.length - 1
        ];
    const ema7 =
        EMA(closes, 7);
    const ema14 =
        EMA(closes, 14);
    const ema25 =
        EMA(closes, 25);
    const ema50 =
        EMA(closes, 50);
    const rsi =
        RSI(closes, 14);
    const atr =
        ATR(
            bars,
            ATR_PERIOD
        );
    let score = 50;
    if (price > ema7)
        score += 8;
    else
        score -= 8;
    if (ema7 > ema14)
        score += 8;
    else
        score -= 8;
    if (ema14 > ema25)
        score += 8;
    else
        score -= 8;
    if (ema25 > ema50)
        score += 8;
    else
        score -= 8;
    if (rsi >= 55)
        score += 8;
    if (rsi <= 45)
        score -= 8;
    score =
        Math.max(
            0,
            Math.min(100, score)
        );
    let direction =
        "NEUTRAL";
    let trend =
        "محايد 🟡";
    if (score >= 60) {
        direction = "UP";
        trend = "صاعد 🟢";
    }
    if (score <= 40) {
        direction = "DOWN";
        trend = "هابط 🔴";
    }
    return {
        price,
        ema7,
        ema14,
        ema25,
        ema50,
        rsi,
        atr,
        score,
        direction,
        trend
    };
}
// ============================================================
// 8 ATR TARGETS
// ============================================================
function makeTargets(
    price,
    atr,
    direction
) {
    const multipliers = [
        0.50,
        0.90,
        1.30,
        1.80,
        2.40,
        3.10,
        4.00,
        5.00
    ];
    return multipliers.map(
        (multiplier, index) => {
            const target =
                direction === "UP"
                    ? price +
                      atr *
                      multiplier
                    : Math.max(
                        0,
                        price -
                        atr *
                        multiplier
                    );
            return {
                number:
                    index + 1,
                multiplier,
                price:
                    target
            };
        }
    );
}
// ============================================================
// INTRADAY DATA
// ============================================================
async function getIntraday(
    symbol
) {
    const to =
        Math.floor(
            Date.now() / 1000
        );
    const from =
        to -
        7 * 24 * 60 * 60;
    try {
        const data =
            await eodhd(
                `/api/intraday/${encodeURIComponent(symbol)}`,
                {
                    interval: "5m",
                    from,
                    to
                }
            );
        return Array.isArray(data)
            ? data
            : [];
    } catch {
        return [];
    }
}
// ============================================================
// NEWS
// ============================================================
async function getNews(
    symbol
) {
    try {
        const data =
            await eodhd(
                "/api/news",
                {
                    s: symbol,
                    offset: 0,
                    limit: 3
                }
            );
        if (
            !Array.isArray(data)
        ) {
            return [];
        }
        return data.map(
            item => ({
                title:
                    item.titleAr ||
                    item.title_ar ||
                    item.title ||
                    "خبر",
                source:
                    item.source ||
                    item.site ||
                    "EODHD",
                date:
                    item.date ||
                    ""
            })
        );
    } catch {
        return [];
    }
}
// ============================================================
// ANALYZE SYMBOL
// ============================================================
async function analyze(
    symbol,
    market
) {
    const bars =
        await getIntraday(
            symbol
        );
    if (
        bars.length <
        MIN_BARS
    ) {
        return null;
    }
    const ai =
        AI_PRO_MAX(bars);
    if (!ai)
        return null;
    const liq =
        liquidity(bars);
    const sr =
        levels(bars);
    let signal =
        null;
    if (
        ai.direction === "UP" &&
        ai.score >= 60 &&
        liq.ratio >= 1.15
    ) {
        signal =
            "🔥 صعود قوي 🟢";
    }
    if (
        ai.direction === "DOWN" &&
        ai.score <= 40 &&
        liq.ratio >= 1.15
    ) {
        signal =
            "🔴✓ هبوط قوي";
    }
    if (!signal)
        return null;
    return {
        symbol,
        market,
        price:
            ai.price,
        direction:
            ai.direction,
        trend:
            ai.trend,
        signal,
        score:
            ai.score,
        atr:
            ai.atr,
        rsi:
            ai.rsi,
        ema7:
            ai.ema7,
        ema14:
            ai.ema14,
        volume:
            num(
                bars[
                    bars.length - 1
                ].volume
            ),
        liquidity:
            liq,
        support:
            sr.support,
        resistance:
            sr.resistance,
        targets:
            makeTargets(
                ai.price,
                ai.atr,
                ai.direction
            )
    };
}
// ============================================================
// MESSAGE
// ============================================================
function buildMessage(
    result,
    news
) {
    const market =
        result.market === "TASI"
            ? "🇸🇦 تاسي"
            : result.market === "US"
                ? "🇺🇸 الأسهم الأمريكية"
                : "🪙 العملات الرقمية";
    let text = "";
    text +=
        `💀🚀 *AI PRO MAX*\n`;
    text +=
        `━━━━━━━━━━━━━━━━━━\n`;
    text +=
        `${market}\n\n`;
    text +=
        `📌 *الرمز:* \`${result.symbol}\`\n`;
    text +=
        `💰 *السعر:* ${priceFormat(result.price)}\n`;
    text +=
        `🚦 *الإشارة:* ${result.signal}\n`;
    text +=
        `🧠 *الاتجاه:* ${result.trend}\n`;
    text +=
        `📊 *قوة AI:* ${result.score}/100\n`;
    text +=
        `📏 *ATR(14):* ${priceFormat(result.atr)}\n`;
    text +=
        `📈 *RSI:* ${result.rsi.toFixed(2)}\n`;
    text +=
        `💧 *السيولة:* ${result.liquidity.label}\n`;
    text +=
        `💧 *السيولة:* ${result.liquidity.ratio.toFixed(2)}x\n`;
    text +=
        `📦 *الحجم:* ${result.volume.toLocaleString()}\n\n`;
    text +=
        `📍 *الدعم:* ${priceFormat(result.support)}\n`;
    text +=
        `📍 *المقاومة:* ${priceFormat(result.resistance)}\n\n`;
    if (
        result.direction === "UP"
    ) {
        text +=
            `🟢 *الأهداف الصاعدة*\n`;
    } else {
        text +=
            `🔴✓ *الأهداف الهابطة*\n`;
    }
    for (
        const target
        of result.targets
    ) {
        text +=
            `${target.number}️⃣ ` +
            `${priceFormat(target.price)} ` +
            `(ATR × ${target.multiplier})\n`;
    }
    if (
        news &&
        news.length
    ) {
        text +=
            `\n📰 *الأخبار*\n`;
        for (
            const item
            of news
        ) {
            text +=
                `• ${item.title}\n`;
            text +=
                `  المصدر: ${item.source}\n`;
        }
    }
    text +=
        `\n━━━━━━━━━━━━━━━━━━\n`;
    text +=
        `🤖 فحص تلقائي AI PRO MAX`;
    return text;
}
// ============================================================
// SEND TELEGRAM
// ============================================================
async function send(
    message
) {
    for (
        const chatId
        of state.chats
    ) {
        try {
            await bot.sendMessage(
                chatId,
                message,
                {
                    parse_mode:
                        "Markdown",
                    disable_web_page_preview:
                        true
                }
            );
        } catch (error) {
            console.error(
                "Telegram:",
                error.message
            );
        }
    }
}
// ============================================================
// TELEGRAM START
// ============================================================
bot.on(
    "message",
    async message => {
        if (
            !message.chat
        )
            return;
        const chatId =
            message.chat.id;
        state.chats.add(
            chatId
        );
        if (
            message.text ===
            "/start"
        ) {
            await bot.sendMessage(
                chatId,
                [
                    "💀🚀 AI PRO MAX",
                    "",
                    "تم تفعيل البوت.",
                    "",
                    "🇸🇦 تاسي كامل",
                    "🇺🇸 الأسهم الأمريكية",
                    "🪙 العملات الرقمية",
                    "",
                    "🧠 AI PRO MAX",
                    "📏 ATR(14)",
                    "🎯 8 أهداف",
                    "📍 دعم ومقاومة",
                    "💧 سيولة",
                    "📰 أخبار EODHD",
                    "",
                    "♾️ الفحص تلقائي",
                    "ولا يحتاج /scan"
                ].join("\n")
            );
        }
    }
);
// ============================================================
// LOAD EXCHANGE LIST
// ============================================================
async function loadUniverse(
    exchange
) {
    try {
        const data =
            await eodhd(
                `/api/exchange-symbol-list/${exchange}/`
            );
        if (
            !Array.isArray(data)
        ) {
            return [];
        }
        return data.filter(
            x => x && x.Code
        );
    } catch (error) {
        console.error(
            `Universe ${exchange}:`,
            error.message
        );
        return [];
    }
}
// ============================================================
// LOAD ALL MARKETS
// ============================================================
async function loadAllMarkets() {
    console.log(
        "📥 تحميل القوائم الكاملة..."
    );
    state.universe.us =
        await loadUniverse(
            "US"
        );
    state.universe.crypto =
        await loadUniverse(
            "CC"
        );
    state.universe.tasi =
        await loadUniverse(
            state.exchanges.tasi
        );
    console.log(
        `🇺🇸 US: ${state.universe.us.length}`
    );
    console.log(
        `🇸🇦 TASI: ${state.universe.tasi.length}`
    );
    console.log(
        `🪙 Crypto: ${state.universe.crypto.length}`
    );
}
// ============================================================
// GET QUOTE
// ============================================================
async function quote(
    symbol
) {
    try {
        return await eodhd(
            `/api/real-time/${encodeURIComponent(symbol)}`
        );
    } catch {
        return null;
    }
}
// ============================================================
// CANDIDATES
// ============================================================
async function candidates(
    universe,
    market,
    limit = 150
) {
    const output = [];
    const batchSize = 20;
    for (
        let i = 0;
        i < universe.length;
        i += batchSize
    ) {
        const batch =
            universe.slice(
                i,
                i + batchSize
            );
        const results =
            await Promise.all(
                batch.map(
                    async item => {
                        const symbol =
                            item.Code +
                            "." +
                            (
                                item.Exchange ||
                                ""
                            );
                        const q =
                            await quote(
                                symbol
                            );
                        if (!q)
                            return null;
                        const price =
                            num(
                                q.close ||
                                q.previousClose ||
                                q.price
                            );
                        if (
                            market === "US" &&
                            price <
                            US_MIN_PRICE
                        ) {
                            return null;
                        }
                        return {
                            symbol:
                                symbol.replace(
                                    /\.$/,
                                    ""
                                ),
                            price,
                            change:
                                num(
                                    q.change_p
                                ),
                            volume:
                                num(
                                    q.volume
                                )
                        };
                    }
                )
            );
        for (
            const result
            of results
        ) {
            if (result)
                output.push(result);
        }
        if (
            output.length >=
            limit
        ) {
            break;
        }
        await sleep(100);
    }
    return output
        .sort(
            (a, b) =>
                Math.abs(
                    b.change
                ) -
                Math.abs(
                    a.change
                )
        )
        .slice(
            0,
            limit
        );
}
// ============================================================
// SIGNAL DUPLICATE PROTECTION
// ============================================================
function alreadySent(
    key
) {
    const previous =
        state.sentSignals.get(
            key
        );
    if (!previous)
        return false;
    return (
        Date.now() -
        previous <
        30 * 60 * 1000
    );
}
function markSent(
    key
) {
    state.sentSignals.set(
        key,
        Date.now()
    );
}
// ============================================================
// SCAN MARKET
// ============================================================
async function scanMarket(
    market,
    universe
) {
    console.log(
        `🔎 ${market} scan...`
    );
    const list =
        await candidates(
            universe,
            market,
            150
        );
    console.log(
        `📊 ${market}: ${list.length} مرشح`
    );
    for (
        const item
        of list
    ) {
        try {
            const result =
                await analyze(
                    item.symbol,
                    market
                );
            if (!result)
                continue;
            const key =
                `${market}:${item.symbol}`;
            if (
                alreadySent(key)
            ) {
                continue;
            }
            const news =
                await getNews(
                    item.symbol
                );
            const message =
                buildMessage(
                    result,
                    news
                );
            await send(
                message
            );
            markSent(
                key
            );
            await sleep(150);
        } catch (error) {
            console.error(
                `${market} ${item.symbol}:`,
                error.message
            );
        }
    }
    state.lastScan[
        market.toLowerCase()
    ] =
        new Date().toISOString();
}
// ============================================================
// FULL SCAN
// ============================================================
async function fullScan() {
    if (
        state.running
    ) {
        console.log(
            "⏳ الفحص السابق ما زال يعمل"
        );
        return;
    }
    state.running = true;
    try {
        console.log(
            "\n━━━━━━━━━━━━━━━━━━━━"
        );
        console.log(
            "💀🚀 AI PRO MAX FULL SCAN"
        );
        console.log(
            new Date().toLocaleString(
                "ar-SA"
            )
        );
        console.log(
            "━━━━━━━━━━━━━━━━━━━━"
        );
        await scanMarket(
            "TASI",
            state.universe.tasi
        );
        await scanMarket(
            "US",
            state.universe.us
        );
        await scanMarket(
            "CRYPTO",
            state.universe.crypto
        );
    } catch (error) {
        console.error(
            "❌ FULL SCAN:",
            error
        );
    } finally {
        state.running =
            false;
    }
}
// ============================================================
// START
// ============================================================
async function start() {
    console.log(
        "🚀 تشغيل AI PRO MAX..."
    );
    console.log(
        `🔐 TASI config: ${TASI_CONFIG ? "OK" : "غير محدد"}`
    );
    console.log(
        `🔐 US config: ${US_CONFIG ? "OK" : "غير محدد"}`
    );
    console.log(
        `🔐 Crypto config: ${CRYPTO_CONFIG ? "OK" : "غير محدد"}`
    );
    console.log(
        "🔐 EODHD API: OK"
    );
    await loadAllMarkets();
    console.log(
        "✅ القوائم جاهزة"
    );
    await fullScan();
    setInterval(
        fullScan,
        SCAN_INTERVAL
    );
    console.log(
        "♾️ AI PRO MAX يعمل تلقائيًا 24/7"
    );
}
// ============================================================
// ERROR PROTECTION
// ============================================================
process.on(
    "unhandledRejection",
    error => {
        console.error(
            "Unhandled:",
            error
        );
    }
);
process.on(
    "uncaughtException",
    error => {
        console.error(
            "Uncaught:",
            error
        );
    }
);
// ============================================================
// RUN
// ============================================================
start().catch(
    error => {
        console.error(
            "❌ START ERROR:",
            error
        );
        setTimeout(
            start,
            60 * 1000
        );
    }
);