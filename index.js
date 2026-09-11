
// ============================================================
// 💀🚀 AI PRO MAX — 3 TELEGRAM BOTS / 1 SERVICE
// 🇸🇦 TASI + 🇺🇸 NASDAQ + 🪙 CRYPTO
// ❌ EODHD removed completely
// Node.js 18+
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const fs = require("fs");
const path = require("path");

// ============================================================
// 🔐 Railway variables — فقط توكنات البوتات الثلاثة
// ============================================================
const TASI_CONFIG = String(process.env.TASI_CONFIG || "").trim();
const US_CONFIG = String(process.env.US_CONFIG || "").trim();
const CRYPTO_CONFIG = String(process.env.CRYPTO_CONFIG || "").trim();

const PORT = Number(process.env.PORT || 8080);
const SCAN_MINUTES = 2;
const REQUEST_TIMEOUT_MS = 20000;
const MAX_SYMBOLS = 1000;
const DEEP_CANDIDATES = 12;
const MIN_US_PRICE = 0.20;

// ============================================================
// 🌐 Web
// ============================================================
const app = express();
let scanRunning = false;

app.get("/", (_req, res) => res.json({
    status: "online",
    bot: "AI PRO MAX 💀🚀",
    markets: ["TASI", "NASDAQ", "CRYPTO"],
    scanMinutes: SCAN_MINUTES,
    eodhd: false,
    time: new Date().toISOString()
}));

app.get("/health", (_req, res) => res.json({
    status: "healthy",
    tasi: !!TASI_CONFIG,
    us: !!US_CONFIG,
    crypto: !!CRYPTO_CONFIG,
    eodhd: false,
    scanRunning
}));

app.listen(PORT, "0.0.0.0", () => {
    console.log(`🌐 الخادم يعمل على ${PORT}`);
});

// ============================================================
// 🤖 Telegram
// ============================================================
function getToken(value) {
    if (!value) return "";

    const s = String(value).trim();

    if (!s.startsWith("{")) {
        return s;
    }

    try {
        const x = JSON.parse(s);

        return String(
            x.token ||
            x.telegramToken ||
            x.TELEGRAM_TOKEN ||
            x.botToken ||
            ""
        ).trim();

    } catch {
        return "";
    }
}

const TOKENS = {
    tasi: getToken(TASI_CONFIG),
    us: getToken(US_CONFIG),
    crypto: getToken(CRYPTO_CONFIG)
};

const bots = {
    tasi: null,
    us: null,
    crypto: null
};

// ============================================================
// 💬 Chat IDs
// ============================================================
const chatFile = path.join(process.cwd(), "chat_ids.json");

let chats = {
    tasi: null,
    us: null,
    crypto: null
};

try {
    if (fs.existsSync(chatFile)) {
        chats = {
            ...chats,
            ...JSON.parse(
                fs.readFileSync(chatFile, "utf8")
            )
        };
    }
} catch {}

function saveChats() {
    try {
        fs.writeFileSync(
            chatFile,
            JSON.stringify(chats, null, 2)
        );
    } catch {}
}

// ============================================================
// 🤖 إنشاء البوت
// ============================================================
function createBot(key, market, token) {

    if (!token) {
        console.error(`❌ ${market}: التوكن غير موجود`);
        return null;
    }

    const bot = new TelegramBot(token, {
        polling: true
    });

    bot.onText(/^\/start$/i, async msg => {

        chats[key] = msg.chat.id;

        saveChats();

        await bot.sendMessage(
            msg.chat.id,

            `💀🚀 أهلاً بك في AI PRO MAX\n\n` +

            `✅ البوت يعمل الآن\n` +

            `🔄 الفحص تلقائي وكامل\n` +

            `⏱️ الفحص كل ${SCAN_MINUTES} دقيقة\n` +

            `📊 السوق: ${market}\n\n` +

            `🤖 لن تحتاج إلى تشغيل الفحص يدويًا.`

        ).catch(() => {});
    });

    bot.onText(/^\/status$/i, async msg => {

        await bot.sendMessage(
            msg.chat.id,

            `💀🚀 AI PRO MAX\n\n` +

            `✅ متصل\n` +

            `🔄 الفحص تلقائي\n` +

            `⏱️ كل ${SCAN_MINUTES} دقيقة`

        ).catch(() => {});
    });

    bot.on(
        "polling_error",
        e => console.error(
            `❌ Telegram ${market}: ${e.message}`
        )
    );

    console.log(`🤖 ${market}: تم تشغيل البوت`);

    return bot;
}

// ============================================================
// 🤖 البوتات الثلاثة
// ============================================================
bots.tasi = createBot(
    "tasi",
    "TASI 🇸🇦",
    TOKENS.tasi
);

bots.us = createBot(
    "us",
    "NASDAQ 🇺🇸",
    TOKENS.us
);

bots.crypto = createBot(
    "crypto",
    "CRYPTO 🪙",
    TOKENS.crypto
);

// ============================================================
// 🌐 Yahoo Finance
// ❌ لا EODHD
// ============================================================
const YAHOO =
    "https://query1.finance.yahoo.com";

const UA =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
    "AppleWebKit/537.36 Chrome/126 Safari/537.36";

// ============================================================
// 🌐 طلب بيانات السوق
// ============================================================
async function yahoo(pathname, options = {}) {

    const controller = new AbortController();

    const timer = setTimeout(
        () => controller.abort(),
        REQUEST_TIMEOUT_MS
    );

    try {

        const response = await fetch(
            `${YAHOO}${pathname}`,
            {
                ...options,

                signal: controller.signal,

                headers: {
                    "User-Agent": UA,
                    "Accept": "application/json",
                    ...(options.headers || {})
                }
            }
        );

        const text = await response.text();

        if (!response.ok) {

            throw new Error(
                `Yahoo HTTP ${response.status}: ` +
                text.slice(0, 180)
            );
        }

        return JSON.parse(text);

    } finally {

        clearTimeout(timer);
    }
}

// ============================================================
// 🧰 أدوات
// ============================================================
function sleep(ms) {
    return new Promise(
        resolve => setTimeout(resolve, ms)
    );
}

function n(v) {

    const x = Number(v);

    return Number.isFinite(x) ? x : 0;
}

function money(v) {

    const x = n(v);

    if (x >= 1000) {

        return x.toLocaleString(
            "en-US",
            {
                maximumFractionDigits: 2
            }
        );
    }

    return x
        .toFixed(4)
        .replace(/0+$/, "")
        .replace(/\.$/, "");
}

function pct(v) {

    return `${n(v).toFixed(2)}%`;
}

function fmtVol(v) {

    const x = n(v);

    if (x >= 1e9) {
        return `${(x / 1e9).toFixed(2)}B`;
    }

    if (x >= 1e6) {
        return `${(x / 1e6).toFixed(2)}M`;
    }

    if (x >= 1e3) {
        return `${(x / 1e3).toFixed(2)}K`;
    }

    return x.toFixed(0);
}

// ============================================================
// 📋 قوائم الأسواق
// ============================================================
async function yahooScreener(
    quoteType,
    exchange,
    size = MAX_SYMBOLS
) {

    const body = {

        offset: 0,

        size,

        sortType: "DESC",

        sortField: "intradaymarketcap",

        query: {

            operator: "and",

            operands: [

                {
                    operator: "eq",
                    operands: [
                        "quoteType",
                        quoteType
                    ]
                },

                {
                    operator: "eq",
                    operands: [
                        "exchange",
                        exchange
                    ]
                }

            ]
        },

        userId: "",

        userIdType: "guid"
    };

    const data = await yahoo(
        "/v1/finance/screener",
        {
            method: "POST",

            headers: {
                "Content-Type":
                    "application/json"
            },

            body: JSON.stringify(body)
        }
    );

    const rows =
        data
            ?.finance
            ?.result
            ?.[0]
            ?.quotes || [];

    return rows

        .map(x => ({

            symbol:
                String(
                    x.symbol || ""
                ),

            name:
                x.longName ||
                x.shortName ||
                x.symbol ||
                ""

        }))

        .filter(
            x => x.symbol
        );
}

// ============================================================
// 📊 الأسواق
// ============================================================
let universes = {

    tasi: [],

    us: [],

    crypto: []

};

// ============================================================
// 🔄 تحديث القوائم
// ============================================================
async function loadUniverses() {

    console.log(
        "🔄 تحديث قوائم الأسواق..."
    );

    // ========================================================
    // 🇸🇦 TASI
    // ========================================================
    try {

        const rows =
            await yahooScreener(
                "EQUITY",
                "SAU"
            );

        universes.tasi =
            rows.filter(
                x =>
                    /\.SR$/i.test(
                        x.symbol
                    ) ||
                    !x.symbol.includes(".")
            );

        console.log(
            `🇸🇦 TASI: ${universes.tasi.length}`
        );

    } catch (e) {

        console.error(
            `❌ TASI: ${e.message}`
        );
    }

    // ========================================================
    // 🇺🇸 NASDAQ
    // ========================================================
    try {

        const rows =
            await yahooScreener(
                "EQUITY",
                "NMS"
            );

        universes.us = rows;

        console.log(
            `🇺🇸 NASDAQ: ${universes.us.length}`
        );

    } catch (e) {

        console.error(
            `❌ NASDAQ: ${e.message}`
        );
    }

    // ========================================================
    // 🪙 CRYPTO
    // ========================================================
    try {

        const rows =
            await yahooScreener(
                "CRYPTOCURRENCY",
                "CCC"
            );

        universes.crypto =
            rows;

        console.log(
            `🪙 CRYPTO: ${universes.crypto.length}`
        );

    } catch (e) {

        console.error(
            `❌ CRYPTO: ${e.message}`
        );
    }
}

// ============================================================
// 💹 الشموع والأسعار
// ============================================================
async function getChart(
    symbol,
    range = "5d",
    interval = "5m"
) {

    const url =
        `/v8/finance/chart/` +
        `${encodeURIComponent(symbol)}` +
        `?range=${range}` +
        `&interval=${interval}` +
        `&includePrePost=false` +
        `&events=div%2Csplits`;

    const data =
        await yahoo(url);

    const result =
        data
            ?.chart
            ?.result
            ?.[0];

    if (!result) {

        throw new Error(
            `لا توجد بيانات ${symbol}`
        );
    }

    const meta =
        result.meta || {};

    const quote =
        result
            .indicators
            ?.quote
            ?.[0] || {};

    const timestamps =
        result.timestamp || [];

    const rows = [];

    for (
        let i = 0;
        i < timestamps.length;
        i++
    ) {

        rows.push({

            time:
                timestamps[i],

            open:
                n(
                    quote.open?.[i]
                ),

            high:
                n(
                    quote.high?.[i]
                ),

            low:
                n(
                    quote.low?.[i]
                ),

            close:
                n(
                    quote.close?.[i]
                ),

            volume:
                n(
                    quote.volume?.[i]
                )
        });
    }

    return {

        meta,

        rows:
            rows.filter(
                x => x.close > 0
            )
    };
}

// ============================================================
// 📈 EMA
// ============================================================
function ema(values, length) {

    if (!values.length) {
        return 0;
    }

    const k =
        2 / (length + 1);

    let value =
        values[0];

    for (
        let i = 1;
        i < values.length;
        i++
    ) {

        value =
            values[i] * k +
            value * (1 - k);
    }

    return value;
}

// ============================================================
// 📉 RSI
// ============================================================
function rsi(
    values,
    length = 14
) {

    if (
        values.length <= length
    ) {

        return 50;
    }

    let gain = 0;

    let loss = 0;

    for (
        let i = 1;
        i <= length;
        i++
    ) {

        const d =
            values[i] -
            values[i - 1];

        if (d >= 0) {

            gain += d;

        } else {

            loss -= d;
        }
    }

    gain /= length;

    loss /= length;

    for (
        let i = length + 1;
        i < values.length;
        i++
    ) {

        const d =
            values[i] -
            values[i - 1];

        gain =
            (
                gain * (length - 1) +
                Math.max(d, 0)
            ) / length;

        loss =
            (
                loss * (length - 1) +
                Math.max(-d, 0)
            ) / length;
    }

    if (!loss) {

        return 100;
    }

    return 100 -
        (
            100 /
            (
                1 +
                gain / loss
            )
        );
}

// ============================================================
// 📐 ATR
// ============================================================
function atr(
    rows,
    length = 14
) {

    if (
        rows.length <
        length + 1
    ) {

        return 0;
    }

    const tr = [];

    for (
        let i = 1;
        i < rows.length;
        i++
    ) {

        tr.push(
            Math.max(

                rows[i].high -
                rows[i].low,

                Math.abs(
                    rows[i].high -
                    rows[i - 1].close
                ),

                Math.abs(
                    rows[i].low -
                    rows[i - 1].close
                )
            )
        );
    }

    return tr
        .slice(-length)
        .reduce(
            (a, b) => a + b,
            0
        ) / length;
}

// ============================================================
// 📍 الدعم والمقاومة
// ============================================================
function supportResistance(rows) {

    const recent =
        rows.slice(-80);

    const lows =
        recent
            .map(x => x.low)
            .filter(x => x > 0);

    const highs =
        recent
            .map(x => x.high)
            .filter(x => x > 0);

    return {

        support:
            lows.length
                ? Math.min(...lows)
                : 0,

        resistance:
            highs.length
                ? Math.max(...highs)
                : 0
    };
}

// ============================================================
// 💧 السيولة
// ============================================================
function liquidity(rows) {

    const volumes =
        rows
            .map(x => x.volume)
            .filter(x => x > 0);

    if (!volumes.length) {

        return {

            current: 0,

            avg: 0,

            ratio: 0,

            label:
                "غير متوفر"
        };
    }

    const current =
        volumes.at(-1);

    const base =
        volumes.slice(-21, -1);

    const avg =
        base.length
            ? base.reduce(
                (a, b) => a + b,
                0
            ) / base.length
            : current;

    const ratio =
        avg
            ? current / avg
            : 0;

    let label =
        "سيولة طبيعية";

    if (ratio >= 2) {

        label =
            "سيولة قوية جدًا 💧🔥";

    } else if (ratio >= 1.3) {

        label =
            "سيولة قوية 💧";

    } else if (ratio < 0.8) {

        label =
            "سيولة ضعيفة";
    }

    return {

        current,

        avg,

        ratio,

        label
    };
}

// ============================================================
// 🧠 التحليل
// ============================================================
function analyze(
    rows,
    meta
) {

    if (
        rows.length < 30
    ) {

        return null;
    }

    const close =
        rows.map(
            x => x.close
        );

    const price =
        n(
            meta.regularMarketPrice
        ) ||
        close.at(-1);

    const previous =
        n(
            meta.previousClose
        ) ||
        close.at(-2) ||
        price;

    const change =
        previous
            ? (
                (price - previous) /
                previous
            ) * 100
            : 0;

    const ema8 =
        ema(close, 8);

    const ema21 =
        ema(close, 21);

    const ema50 =
        ema(close, 50);

    const r =
        rsi(close, 14);

    const a =
        atr(rows, 14);

    const sr =
        supportResistance(rows);

    const liq =
        liquidity(rows);

    let score = 50;

    score +=
        price > ema8
            ? 8
            : -8;

    score +=
        ema8 > ema21
            ? 10
            : -10;

    score +=
        ema21 > ema50
            ? 12
            : -12;

    score +=
        r >= 50 && r < 80
            ? 8
            : r < 50
                ? -8
                : -2;

    score +=
        liq.ratio >= 1.5
            ? 7
            : liq.ratio < 0.7
                ? -4
                : 0;

    score +=
        change >= 2
            ? 5
            : change <= -2
                ? -5
                : 0;

    score =
        Math.max(
            0,
            Math.min(
                100,
                score
            )
        );

    const up =
        score >= 55;

    let signal =
        "مراقبة";

    if (score >= 78) {

        signal =
            "شراء قوي 🟢";

    } else if (score <= 25) {

        signal =
            "بيع قوي 🔴";

    } else if (score >= 65) {

        signal =
            "شراء 🟢";

    } else if (score <= 40) {

        signal =
            "بيع 🔴";
    }

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

    const targets =
        multipliers.map(
            (m, i) => ({

                name:
                    `TP${i + 1}`,

                price:
                    up
                        ? price + a * m
                        : price - a * m

            })
        );

    return {

        price,

        change,

        ema8,

        ema21,

        ema50,

        rsi: r,

        atr: a,

        score,

        up,

        signal,

        sr,

        liq,

        targets
    };
}

// ============================================================
// 📲 رسالة التنبيه
// ============================================================
function message(
    market,
    item,
    a
) {

    const flag =
        market === "TASI"
            ? "🇸🇦"
            : market === "NASDAQ"
                ? "🇺🇸"
                : "🪙";

    const mark =
        a.up
            ? "🟢"
            : "🔴✓";

    let text =
        `💀🚀 AI PRO MAX\n` +
        `━━━━━━━━━━━━━━━━━━\n`;

    text +=
        `${flag} ${market}\n`;

    text +=
        `📌 ${item.symbol}` +
        ` — ${item.name}\n`;

    text +=
        `💰 السعر: ${money(a.price)}\n`;

    text +=
        `📊 الإشارة: ${a.signal}\n`;

    text +=
        `🧠 AI: ${a.score}/100\n`;

    text +=
        `${
            a.up
                ? "🟢 الاتجاه العام صاعد"
                : "🔴 الاتجاه العام هابط"
        }\n`;

    text +=
        `📈 التغير: ${pct(a.change)}\n`;

    text +=
        `💧 السيولة: ${a.liq.label}\n`;

    text +=
        `💧 الحجم: ` +
        `${fmtVol(a.liq.current)} | ` +
        `متوسط: ${fmtVol(a.liq.avg)} | ` +
        `${a.liq.ratio.toFixed(2)}x\n`;

    text +=
        `📉 RSI14: ${a.rsi.toFixed(2)}\n`;

    text +=
        `📐 ATR14: ${money(a.atr)}\n`;

    text +=
        `📍 الدعم: ${money(a.sr.support)}\n`;

    text +=
        `📍 المقاومة: ${money(a.sr.resistance)}\n\n`;

    text +=
        `🎯 أهداف ATR الديناميكية ${mark}\n`;

    for (
        const target of a.targets
    ) {

        text +=
            `${mark} ` +
            `${target.name}: ` +
            `${money(target.price)}\n`;
    }

    text +=
        `\n━━━━━━━━━━━━━━━━━━\n` +
        `🤖 فحص تلقائي كل ` +
        `${SCAN_MINUTES} دقيقة`;

    return text;
}

// ============================================================
// 📤 إرسال
// ============================================================
async function send(
    key,
    text
) {

    if (
        !bots[key] ||
        !chats[key]
    ) {

        return;
    }

    await bots[key]
        .sendMessage(
            chats[key],
            text,
            {
                disable_web_page_preview:
                    true
            }
        )
        .catch(
            e =>
                console.error(
                    `❌ Telegram: ${e.message}`
                )
        );
}

// ============================================================
// 🔔 منع التكرار
// ============================================================
const lastAlert =
    new Map();

// ============================================================
// 🔎 فحص السوق
// ============================================================
async function scanMarket(
    market,
    items,
    botKey
) {

    if (!items.length) {

        console.log(
            `⚠️ ${market}: لا توجد رموز`
        );

        return;
    }

    const candidates = [];

    for (
        const item of items
    ) {

        try {

            const chart =
                await getChart(
                    item.symbol,
                    "5d",
                    "5m"
                );

            const analysis =
                analyze(
                    chart.rows,
                    chart.meta
                );

            if (!analysis) {
                continue;
            }

            if (
                market === "NASDAQ" &&
                analysis.price <
                    MIN_US_PRICE
            ) {

                continue;
            }

            if (
                analysis.score >= 62 ||
                Math.abs(
                    analysis.change
                ) >= 3
            ) {

                candidates.push({
                    item,
                    analysis
                });
            }

        } catch {}

        await sleep(120);
    }

    candidates.sort(
        (a, b) =>
            b.analysis.score -
            a.analysis.score
    );

    const selected =
        candidates.slice(
            0,
            DEEP_CANDIDATES
        );

    for (
        const candidate of selected
    ) {

        const a =
            candidate.analysis;

        const strong =
            a.signal ===
                "شراء قوي 🟢" ||
            a.signal ===
                "بيع قوي 🔴";

        if (!strong) {
            continue;
        }

        const alertKey =
            `${market}:` +
            `${candidate.item.symbol}:` +
            `${a.signal}:` +
            `${Math.floor(
                a.score / 5
            )}`;

        const previousKey =
            `${market}:` +
            `${candidate.item.symbol}`;

        if (
            lastAlert.get(
                previousKey
            ) === alertKey
        ) {

            continue;
        }

        lastAlert.set(
            previousKey,
            alertKey
        );

        await send(
            botKey,
            message(
                market,
                candidate.item,
                a
            )
        );
    }

    console.log(
        `🔎 ${market}: ` +
        `${items.length} رمز | ` +
        `${candidates.length} مرشح | ` +
        `${selected.length} تحليل نهائي`
    );
}

// ============================================================
// 🚀 دورة الفحص
// ============================================================
async function fullScan() {

    if (scanRunning) {

        console.log(
            "⏭️ توجد دورة فحص سابقة"
        );

        return;
    }

    scanRunning = true;

    const started =
        Date.now();

    try {

        if (
            !universes.tasi.length ||
            !universes.us.length ||
            !universes.crypto.length
        ) {

            await loadUniverses();
        }

        await scanMarket(
            "TASI",
            universes.tasi,
            "tasi"
        );

        await scanMarket(
            "NASDAQ",
            universes.us,
            "us"
        );

        await scanMarket(
            "CRYPTO",
            universes.crypto,
            "crypto"
        );

        console.log(
            `✅ اكتملت الدورة خلال ` +
            `${(
                (Date.now() - started) /
                1000
            ).toFixed(1)} ثانية`
        );

    } catch (e) {

        console.error(
            `❌ دورة الفحص: ${e.message}`
        );

    } finally {

        scanRunning = false;
    }
}

// ============================================================
// ▶️ التشغيل
// ============================================================
async function start() {

    console.log(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    );

    console.log(
        "💀🚀 AI PRO MAX — 3 BOTS / 1 CODE"
    );

    console.log(
        "❌ EODHD: REMOVED"
    );

    console.log(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    );

    console.log(
        TOKENS.tasi
            ? "✅ TASI Telegram"
            : "❌ TASI Telegram"
    );

    console.log(
        TOKENS.us
            ? "✅ US Telegram"
            : "❌ US Telegram"
    );

    console.log(
        TOKENS.crypto
            ? "✅ CRYPTO Telegram"
            : "❌ CRYPTO Telegram"
    );

    await loadUniverses();

    setTimeout(
        () =>
            fullScan()
                .catch(console.error),
        5000
    );

    setInterval(
        () =>
            fullScan()
                .catch(console.error),
        SCAN_MINUTES *
        60 *
        1000
    );

    setInterval(
        () =>
            loadUniverses()
                .catch(
                    e =>
                        console.error(
                            `❌ تحديث القوائم: ${e.message}`
                        )
                ),
        60 *
        60 *
        1000
    );
}

start().catch(
    e =>
        console.error(
            `❌ فشل النظام: ${e.message}`
        )
);