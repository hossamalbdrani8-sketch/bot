
// ============================================================
// 🤖 AI PRO MAX 💀🚀
// TASI + NASDAQ + CRYPTO — 3 TELEGRAM BOTS / 1 SERVICE
// فحص كامل تلقائي كل دقيقتين
// Node.js 18+
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const fs = require("fs");
const path = require("path");

// ============================================================
// 🔐 Railway variables — لا نغيّر أسماء المتغيرات
// ============================================================

const EODHD_API_KEY = String(process.env.EODHD_API_KEY || "").trim();

const TASI_CONFIG = String(process.env.TASI_CONFIG || "").trim();
const US_CONFIG = String(process.env.US_CONFIG || "").trim();
const CRYPTO_CONFIG = String(process.env.CRYPTO_CONFIG || "").trim();

// ============================================================
// ⚙️ الإعدادات
// ============================================================

const PORT = Number(process.env.PORT || 8080);

// 🔄 الفحص تلقائي كل دقيقتين
const SCAN_MINUTES = 2;

// حجم دفعة أسعار السوق
const QUOTE_BATCH_SIZE = Math.max(
    20,
    Math.min(
        100,
        Number(process.env.QUOTE_BATCH_SIZE || 80)
    )
);

// عدد الأسهم التي تنتقل للتحليل العميق
const DEEP_CANDIDATES_PER_MARKET = Math.max(
    1,
    Math.min(
        40,
        Number(process.env.DEEP_CANDIDATES_PER_MARKET || 20)
    )
);

// أقل سعر للسوق الأمريكي
const MIN_US_PRICE = 0.20;

// مهلة طلب EODHD
const REQUEST_TIMEOUT_MS = 30000;

// عدد الأخبار
const NEWS_LIMIT = 3;

// ============================================================
// 🌐 Web Server
// ============================================================

const app = express();

let scanRunning = false;

app.get("/", (_req, res) => {
    res.json({
        status: "online",
        bot: "AI PRO MAX 💀🚀",
        markets: [
            "TASI",
            "NASDAQ",
            "CRYPTO"
        ],
        scanMinutes: SCAN_MINUTES,
        automatic: true,
        time: new Date().toISOString()
    });
});

app.get("/health", (_req, res) => {
    res.json({
        status: "healthy",
        eodhd: Boolean(EODHD_API_KEY),
        tasi: Boolean(TASI_CONFIG),
        us: Boolean(US_CONFIG),
        crypto: Boolean(CRYPTO_CONFIG),
        scanRunning
    });
});

app.listen(
    PORT,
    "0.0.0.0",
    () => {
        console.log(`🌐 الخادم يعمل على ${PORT}`);
    }
);

// ============================================================
// 🔑 Telegram Token
// ============================================================

function getTelegramToken(value) {

    if (!value) return "";

    const text = String(value).trim();

    // إذا كانت القيمة JSON
    if (text.startsWith("{")) {

        try {

            const obj = JSON.parse(text);

            return String(
                obj.token ||
                obj.telegramToken ||
                obj.TELEGRAM_TOKEN ||
                obj.botToken ||
                ""
            ).trim();

        } catch {

            return "";
        }
    }

    // القيمة المباشرة
    return text;
}

// ============================================================
// 🤖 التوكنات
// ============================================================

const TOKENS = {

    tasi: getTelegramToken(TASI_CONFIG),

    us: getTelegramToken(US_CONFIG),

    crypto: getTelegramToken(CRYPTO_CONFIG)

};

// ============================================================
// 💬 حفظ Chat IDs
// ============================================================

const CHAT_FILE = path.join(
    process.cwd(),
    "chat_ids.json"
);

let chatIds = {
    tasi: null,
    us: null,
    crypto: null
};

try {

    if (fs.existsSync(CHAT_FILE)) {

        chatIds = {
            ...chatIds,
            ...JSON.parse(
                fs.readFileSync(
                    CHAT_FILE,
                    "utf8"
                )
            )
        };
    }

} catch {}

function saveChatIds() {

    try {

        fs.writeFileSync(
            CHAT_FILE,
            JSON.stringify(
                chatIds,
                null,
                2
            )
        );

    } catch {}

}

// ============================================================
// 🤖 Telegram Bots
// ============================================================

const bots = {
    tasi: null,
    us: null,
    crypto: null
};

function createBot(
    key,
    label,
    token
) {

    if (!token) {

        console.error(
            `❌ ${label}: التوكن غير موجود`
        );

        return null;
    }

    try {

        const bot = new TelegramBot(
            token,
            {
                polling: true
            }
        );

        // ====================================================
        // /start
        // ====================================================

        bot.onText(
            /^\/start$/i,
            async (msg) => {

                chatIds[key] =
                    msg.chat.id;

                saveChatIds();

                try {

                    await bot.sendMessage(
                        msg.chat.id,

                        `💀🚀 أهلاً بك في AI PRO MAX

` +
                        `✅ البوت يعمل الآن

` +
                        `🔄 الفحص تلقائي وكامل

` +
                        `⏱️ الفحص كل ${SCAN_MINUTES} دقيقة

` +
                        `📊 السوق: ${label}

` +
                        `🤖 لا تحتاج إلى تشغيل الفحص يدويًا.`
                    );

                } catch (e) {

                    console.error(
                        `❌ Telegram ${label}: ${e.message}`
                    );

                }

            }
        );

        // ====================================================
        // /status
        // ====================================================

        bot.onText(
            /^\/status$/i,
            async (msg) => {

                try {

                    await bot.sendMessage(
                        msg.chat.id,

                        `💀🚀 AI PRO MAX

` +
                        `✅ البوت متصل

` +
                        `🔄 الفحص تلقائي

` +
                        `📊 فحص السوق كامل

` +
                        `⏱️ كل ${SCAN_MINUTES} دقائق`
                    );

                } catch {}

            }
        );

        // ====================================================
        // أخطاء Telegram
        // ====================================================

        bot.on(
            "polling_error",
            (e) => {

                console.error(
                    `❌ Telegram ${label}: ${e.message}`
                );

            }
        );

        console.log(
            `🤖 ${label}: تم تشغيل البوت`
        );

        return bot;

    } catch (e) {

        console.error(
            `❌ ${label}: فشل التشغيل — ${e.message}`
        );

        return null;
    }
}

// ============================================================
// 🤖 تشغيل البوتات الثلاثة
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
// 🌐 EODHD API
// ============================================================

async function api(
    pathname,
    params = {},
    retry = 0
) {

    if (!EODHD_API_KEY) {

        throw new Error(
            "EODHD_API_KEY غير موجود"
        );
    }

    const q = new URLSearchParams({

        ...params,

        api_token:
            EODHD_API_KEY,

        fmt: "json"

    });

    const url =
        `https://eodhd.com/api/${pathname}?${q.toString()}`;

    const controller =
        new AbortController();

    const timer =
        setTimeout(
            () => controller.abort(),
            REQUEST_TIMEOUT_MS
        );

    try {

        const response =
            await fetch(
                url,
                {
                    signal:
                        controller.signal
                }
            );

        const text =
            await response.text();

        if (!response.ok) {

            const err =
                new Error(
                    `EODHD HTTP ${response.status}: ${text.slice(0, 300)}`
                );

            err.status =
                response.status;

            // إعادة المحاولة
            if (
                (
                    response.status === 429 ||
                    response.status >= 500
                ) &&
                retry < 2
            ) {

                await sleep(
                    1500 * (retry + 1)
                );

                return api(
                    pathname,
                    params,
                    retry + 1
                );
            }

            throw err;
        }

        try {

            return JSON.parse(text);

        } catch {

            throw new Error(
                "EODHD أرسل JSON غير صالح"
            );
        }

    } finally {

        clearTimeout(timer);
    }
}

// ============================================================
// 🧰 أدوات
// ============================================================

function sleep(ms) {

    return new Promise(
        resolve => setTimeout(
            resolve,
            ms
        )
    );
}

function n(v) {

    const x = Number(v);

    return Number.isFinite(x)
        ? x
        : 0;
}

function money(v) {

    const x = n(v);

    if (!x) return "0";

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

    if (x >= 1e9)
        return `${(x / 1e9).toFixed(2)}B`;

    if (x >= 1e6)
        return `${(x / 1e6).toFixed(2)}M`;

    if (x >= 1e3)
        return `${(x / 1e3).toFixed(2)}K`;

    return x.toFixed(0);
}

function chunk(
    arr,
    size
) {

    const out = [];

    for (
        let i = 0;
        i < arr.length;
        i += size
    ) {

        out.push(
            arr.slice(
                i,
                i + size
            )
        );
    }

    return out;
}

// ============================================================
// 📋 الأسواق
// ============================================================

let universes = {

    tasi: [],

    us: [],

    crypto: []

};

let tasiExchange = "";

// ============================================================
// 🇸🇦 العثور على بورصة تداول
// ============================================================

async function getTasiExchangeCode() {

    const exchanges =
        await api(
            "exchanges-list",
            {}
        );

    const row =
        Array.isArray(exchanges)
            ? exchanges.find(
                x =>
                    /Saudi Stock Exchange|TADAWUL/i.test(
                        `${x.Name || ""} ${x.Code || ""}`
                    )
            )
            : null;

    if (
        !row ||
        !row.Code
    ) {

        throw new Error(
            "لم يتم العثور على كود بورصة تداول في EODHD"
        );
    }

    return String(
        row.Code
    );
}

// ============================================================
// 📋 تحميل قوائم الأسواق
// ============================================================

async function loadUniverses() {

    console.log(
        "🔄 تحديث قوائم الأسواق الكاملة..."
    );

    // ========================================================
    // 🇸🇦 TASI
    // ========================================================

    try {

        tasiExchange =
            await getTasiExchangeCode();

        const data =
            await api(
                `exchange-symbol-list/${encodeURIComponent(tasiExchange)}`,
                {
                    type: "common_stock"
                }
            );

        universes.tasi =
            (
                Array.isArray(data)
                    ? data
                    : []
            )
                .filter(
                    x =>
                        x &&
                        x.Code
                )
                .map(
                    x => ({
                        code:
                            String(x.Code),

                        name:
                            x.Name ||
                            x.Code,

                        exchange:
                            tasiExchange
                    })
                );

        console.log(
            `🇸🇦 TASI: ${universes.tasi.length} سهم — exchange=${tasiExchange}`
        );

    } catch (e) {

        console.error(
            `❌ TASI universe: ${e.message}`
        );
    }

    // ========================================================
    // 🇺🇸 NASDAQ
    // ========================================================

    try {

        const data =
            await api(
                "exchange-symbol-list/NASDAQ",
                {
                    type: "common_stock"
                }
            );

        universes.us =
            (
                Array.isArray(data)
                    ? data
                    : []
            )
                .filter(
                    x =>
                        x &&
                        x.Code
                )
                .map(
                    x => ({
                        code:
                            String(x.Code),

                        name:
                            x.Name ||
                            x.Code,

                        exchange:
                            "NASDAQ"
                    })
                );

        console.log(
            `🇺🇸 NASDAQ: ${universes.us.length} سهم`
        );

    } catch (e) {

        console.error(
            `❌ NASDAQ universe: ${e.message}`
        );
    }

    // ========================================================
    // 🪙 CRYPTO
    // ========================================================

    try {

        const data =
            await api(
                "exchange-symbol-list/CC",
                {}
            );

        universes.crypto =
            (
                Array.isArray(data)
                    ? data
                    : []
            )
                .filter(
                    x =>
                        x &&
                        x.Code
                )
                .map(
                    x => ({
                        code:
                            String(x.Code),

                        name:
                            x.Name ||
                            x.Code,

                        exchange:
                            "CC"
                    })
                );

        console.log(
            `🪙 CRYPTO: ${universes.crypto.length} زوج`
        );

    } catch (e) {

        console.error(
            `❌ CRYPTO universe: ${e.message}`
        );
    }
}

// ============================================================
// 💹 تكوين رمز EODHD
// ============================================================

function fullSymbol(
    item,
    market
) {

    if (
        market === "TASI"
    ) {

        return `${item.code}.${item.exchange}`;
    }

    if (
        market === "NASDAQ"
    ) {

        return `${item.code}.US`;
    }

    return `${item.code}.CC`;
}

// ============================================================
// 💹 جلب أسعار السوق بالكامل
// ============================================================

async function quoteBatch(
    symbols
) {

    if (!symbols.length)
        return [];

    const first =
        symbols[0];

    const rest =
        symbols
            .slice(1)
            .join(",");

    return api(
        `real-time/${encodeURIComponent(first)}`,
        rest
            ? { s: rest }
            : {}
    );
}

async function getFullMarketQuotes(
    market,
    items
) {

    const result = [];

    const symbols =
        items.map(
            x =>
                fullSymbol(
                    x,
                    market
                )
        );

    const batches =
        chunk(
            symbols,
            QUOTE_BATCH_SIZE
        );

    for (
        let i = 0;
        i < batches.length;
        i++
    ) {

        try {

            const rows =
                await quoteBatch(
                    batches[i]
                );

            if (
                Array.isArray(rows)
            ) {

                result.push(
                    ...rows
                );
            }

        } catch (e) {

            console.error(
                `❌ ${market} quote batch ${i + 1}/${batches.length}: ${e.message}`
            );
        }

        if (
            i <
            batches.length - 1
        ) {

            await sleep(150);
        }
    }

    return result;
}

// ============================================================
// 🧠 AI PRO MAX — التقييم الأولي
// ============================================================

function quoteScore(q) {

    const price =
        n(q.close);

    const open =
        n(q.open);

    const high =
        n(q.high);

    const low =
        n(q.low);

    const prev =
        n(q.previousClose);

    const volume =
        n(q.volume);

    if (
        price <= 0 ||
        prev <= 0
    ) {

        return null;
    }

    const change =
        n(
            q.change_p ??
            (
                (
                    price - prev
                ) /
                prev
            ) *
            100
        );

    const range =
        Math.max(
            high - low,
            0
        );

    const location =
        range > 0
            ? (
                (
                    price - low
                ) /
                range
            ) *
            100
            : 50;

    const openBias =
        open > 0
            ? (
                (
                    price - open
                ) /
                open
            ) *
            100
            : 0;

    let score = 50;

    if (
        change > 0
    ) {

        score +=
            Math.min(
                20,
                change * 2.5
            );

    } else {

        score -=
            Math.min(
                20,
                Math.abs(change) * 2.5
            );
    }

    if (
        openBias > 0
    ) {

        score +=
            Math.min(
                10,
                openBias * 2
            );

    } else {

        score -=
            Math.min(
                10,
                Math.abs(openBias) * 2
            );
    }

    if (
        location >= 70
    ) {

        score += 12;

    } else if (
        location <= 30
    ) {

        score -= 12;
    }

    if (
        volume > 0
    ) {

        score += 3;
    }

    score =
        Math.max(
            0,
            Math.min(
                100,
                score
            )
        );

    let direction =
        "محايد";

    if (
        score >= 62
    ) {

        direction =
            "صاعد";
    }

    if (
        score <= 38
    ) {

        direction =
            "هابط";
    }

    return {

        price,

        open,

        high,

        low,

        prev,

        volume,

        change,

        openBias,

        location,

        score,

        direction

    };
}

// ============================================================
// 📐 EMA
// ============================================================

function ema(
    values,
    period
) {

    if (
        !values.length
    ) {

        return 0;
    }

    const k =
        2 /
        (
            period + 1
        );

    let e =
        values[0];

    for (
        let i = 1;
        i < values.length;
        i++
    ) {

        e =
            values[i] * k +
            e * (1 - k);
    }

    return e;
}

// ============================================================
// 📊 RSI
// ============================================================

function rsi(
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

        const d =
            values[i] -
            values[i - 1];

        if (
            d >= 0
        ) {

            gain += d;

        } else {

            loss +=
                Math.abs(d);
        }
    }

    let ag =
        gain / period;

    let al =
        loss / period;

    for (
        let i = period + 1;
        i < values.length;
        i++
    ) {

        const d =
            values[i] -
            values[i - 1];

        const g =
            d > 0
                ? d
                : 0;

        const l =
            d < 0
                ? Math.abs(d)
                : 0;

        ag =
            (
                ag * (period - 1) +
                g
            ) /
            period;

        al =
            (
                al * (period - 1) +
                l
            ) /
            period;
    }

    return al === 0
        ? 100
        : 100 -
            (
                100 /
                (
                    1 +
                    ag / al
                )
            );
}

// ============================================================
// 📐 ATR14
// ============================================================

function atr(
    candles,
    period = 14
) {

    if (
        candles.length <
        period + 1
    ) {

        return 0;
    }

    const tr = [];

    for (
        let i = 1;
        i < candles.length;
        i++
    ) {

        const h =
            n(candles[i].high);

        const l =
            n(candles[i].low);

        const pc =
            n(
                candles[i - 1].close
            );

        tr.push(
            Math.max(
                h - l,
                Math.abs(
                    h - pc
                ),
                Math.abs(
                    l - pc
                )
            )
        );
    }

    let a =
        tr
            .slice(
                0,
                period
            )
            .reduce(
                (s, x) =>
                    s + x,
                0
            ) /
        period;

    for (
        let i = period;
        i < tr.length;
        i++
    ) {

        a =
            (
                a *
                (period - 1) +
                tr[i]
            ) /
            period;
    }

    return a;
}

// ============================================================
// 📍 الدعم والمقاومة
// ============================================================

function sr(
    candles
) {

    const recent =
        candles.slice(-80);

    let support =
        Infinity;

    let resistance =
        0;

    for (
        const c of recent
    ) {

        const l =
            n(c.low);

        const h =
            n(c.high);

        if (
            l > 0
        ) {

            support =
                Math.min(
                    support,
                    l
                );
        }

        resistance =
            Math.max(
                resistance,
                h
            );
    }

    return {

        support:
            Number.isFinite(
                support
            )
                ? support
                : 0,

        resistance

    };
}

// ============================================================
// 💧 السيولة
// ============================================================

function liquidity(
    candles
) {

    const vols =
        candles
            .map(
                c =>
                    n(c.volume)
            )
            .filter(
                v =>
                    v > 0
            );

    if (
        !vols.length
    ) {

        return {

            current: 0,

            avg: 0,

            ratio: 0,

            label:
                "غير متوفر"

        };
    }

    const current =
        vols[
            vols.length - 1
        ];

    const base =
        vols.slice(
            -21,
            -1
        );

    const avg =
        base.length
            ? base.reduce(
                (a, b) =>
                    a + b,
                0
            ) /
            base.length
            : current;

    const ratio =
        avg > 0
            ? current / avg
            : 0;

    let label =
        "سيولة ضعيفة";

    if (
        ratio >= 2
    ) {

        label =
            "سيولة قوية جدًا 💧🔥";

    } else if (
        ratio >= 1.3
    ) {

        label =
            "سيولة قوية 💧";

    } else if (
        ratio >= 0.8
    ) {

        label =
            "سيولة طبيعية";
    }

    return {

        current,

        avg,

        ratio,

        label

    };
}

// ============================================================
// 🧠 التحليل العميق
// ============================================================

function deepAnalyze(
    candles,
    quote
) {

    if (
        !Array.isArray(candles) ||
        candles.length < 30
    ) {

        return null;
    }

    const closes =
        candles
            .map(
                c =>
                    n(c.close)
            )
            .filter(Boolean);

    const price =
        closes.at(-1) ||
        quote.price;

    const e8 =
        ema(
            closes,
            8
        );

    const e21 =
        ema(
            closes,
            21
        );

    const e50 =
        ema(
            closes,
            50
        );

    const r =
        rsi(
            closes,
            14
        );

    const a =
        atr(
            candles,
            14
        );

    const levels =
        sr(candles);

    const liq =
        liquidity(candles);

    let score =
        quote.score;

    if (
        price > e8
    ) {

        score += 7;

    } else {

        score -= 7;
    }

    if (
        e8 > e21
    ) {

        score += 8;

    } else {

        score -= 8;
    }

    if (
        e21 > e50
    ) {

        score += 10;

    } else {

        score -= 10;
    }

    if (
        r >= 50 &&
        r < 80
    ) {

        score += 8;

    } else if (
        r < 50
    ) {

        score -= 8;
    }

    if (
        liq.ratio >= 1.5
    ) {

        score += 5;

    } else if (
        liq.ratio < 0.7
    ) {

        score -= 3;
    }

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

    if (
        score >= 78
    ) {

        signal =
            "شراء قوي 🟢";

    } else if (
        score >= 65
    ) {

        signal =
            "شراء 🟢";

    } else if (
        score <= 25
    ) {

        signal =
            "بيع قوي 🔴";

    } else if (
        score <= 40
    ) {

        signal =
            "بيع 🔴";
    }

    // ========================================================
    // 🎯 8 أهداف ATR ديناميكية
    // ========================================================

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

        e8,

        e21,

        e50,

        rsi: r,

        atr: a,

        score,

        signal,

        up,

        support:
            levels.support,

        resistance:
            levels.resistance,

        liquidity:
            liq,

        targets

    };
}

// ============================================================
// 📈 بيانات 5 دقائق
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
        (
            3 *
            24 *
            60 *
            60
        );

    return api(
        `intraday/${encodeURIComponent(symbol)}`,
        {

            interval:
                "5m",

            from:
                String(from),

            to:
                String(to),

            order:
                "a"

        }
    );
}

// ============================================================
// 📰 الأخبار — EODHD فقط
// ============================================================

async function getNews(
    symbol
) {

    try {

        const rows =
            await api(
                "news",
                {

                    s:
                        symbol,

                    limit:
                        NEWS_LIMIT,

                    offset:
                        0

                }
            );

        if (
            !Array.isArray(rows)
        ) {

            return [];
        }

        return rows
            .slice(
                0,
                NEWS_LIMIT
            )
            .map(
                x => ({

                    title:
                        x.titleAr ||
                        x.title_ar ||
                        x.titleArabic ||
                        x.translation ||
                        x.title ||
                        "خبر",

                    source:
                        x.source ||
                        x.site ||
                        "EODHD",

                    link:
                        x.link ||
                        ""

                })
            );

    } catch (e) {

        console.error(
            `⚠️ News ${symbol}: ${e.message}`
        );

        return [];
    }
}

// ============================================================
// 📲 رسالة الإشارة
// ============================================================

function signalMessage(
    market,
    item,
    q,
    a,
    news
) {

    const flag =
        market === "TASI"
            ? "🇸🇦"
            : market === "NASDAQ"
                ? "🇺🇸"
                : "🪙";

    const trend =
        a.up
            ? "🟢 الاتجاه العام صاعد"
            : "🔴 الاتجاه العام هابط";

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
        `📌 ${item.code}` +
        (
            item.name
                ? ` — ${item.name}`
                : ""
        ) +
        `\n`;

    text +=
        `💰 السعر: ${money(a.price)}\n`;

    text +=
        `📊 الإشارة: ${a.signal}\n`;

    text +=
        `🧠 AI: ${a.score}/100\n`;

    text +=
        `${trend}\n`;

    text +=
        `📈 التغير: ${pct(q.change)}\n`;

    text +=
        `💧 السيولة: ${a.liquidity.label}\n`;

    text +=
        `💧 الحجم: ${fmtVol(a.liquidity.current)}` +
        ` | متوسط: ${fmtVol(a.liquidity.avg)}` +
        ` | ${a.liquidity.ratio.toFixed(2)}x\n`;

    text +=
        `📉 RSI14: ${a.rsi.toFixed(2)}\n`;

    text +=
        `📐 ATR14: ${money(a.atr)}\n`;

    text +=
        `📍 الدعم: ${money(a.support)}\n`;

    text +=
        `📍 المقاومة: ${money(a.resistance)}\n`;

    text +=
        `\n🎯 أهداف ATR الديناميكية ${mark}\n`;

    for (
        const t of a.targets
    ) {

        text +=
            `${mark} ${t.name}: ${money(t.price)}\n`;
    }

    // ========================================================
    // 📰 الأخبار
    // ========================================================

    if (
        news.length
    ) {

        text +=
            `\n📰 الأخبار من EODHD\n`;

        for (
            const x of news
        ) {

            text +=
                `• ${x.title}\n`;
        }
    }

    text +=
        `\n━━━━━━━━━━━━━━━━━━\n` +
        `🤖 فحص السوق كامل تلقائيًا\n` +
        `⏱️ الفحص كل ${SCAN_MINUTES} دقيقة`;

    return text;
}

// ============================================================
// 📲 إرسال Telegram
// ============================================================

async function send(
    bot,
    chatId,
    text
) {

    if (
        !bot ||
        !chatId
    ) {

        return false;
    }

    try {

        await bot.sendMessage(
            chatId,
            text,
            {
                disable_web_page_preview:
                    true
            }
        );

        return true;

    } catch (e) {

        console.error(
            `❌ إرسال Telegram: ${e.message}`
        );

        return false;
    }
}

// ============================================================
// 🧠 Full Market Scanner
// ============================================================

const lastAlert =
    new Map();

function shouldDeepAnalyze(
    q,
    market
) {

    if (!q)
        return false;

    // 🇺🇸 أقل سعر
    if (
        market === "NASDAQ" &&
        q.price < MIN_US_PRICE
    ) {

        return false;
    }

    // ========================================================
    // المرشح ينتقل للتحليل العميق
    // ========================================================

    return (
        q.score >= 62 ||
        q.change >= 3 ||
        (
            q.volume > 0 &&
            q.location >= 80
        )
    );
}

// ============================================================
// 🔔 منع تكرار نفس التنبيه
// ============================================================

function alertKey(
    market,
    code,
    a
) {

    const bucket =
        Math.floor(
            a.score / 5
        );

    const side =
        a.up
            ? "UP"
            : "DOWN";

    return (
        `${market}:${code}:${side}:${bucket}`
    );
}

// ============================================================
// 🔎 فحص سوق
// ============================================================

async function scanMarket(
    market,
    items,
    botKey
) {

    if (
        !items.length
    ) {

        return {

            quotes: 0,

            candidates: 0,

            alerts: 0

        };
    }

    const bot =
        bots[botKey];

    const chatId =
        chatIds[botKey];

    // ========================================================
    // 💹 فحص جميع الأسعار
    // ========================================================

    const rawQuotes =
        await getFullMarketQuotes(
            market,
            items
        );

    const byCode =
        new Map();

    for (
        const q of rawQuotes
    ) {

        if (
            q &&
            q.code
        ) {

            byCode.set(
                String(
                    q.code
                ).toUpperCase(),
                q
            );
        }
    }

    // ========================================================
    // 🧠 تقييم كامل السوق
    // ========================================================

    const candidates = [];

    for (
        const item of items
    ) {

        const symbol =
            fullSymbol(
                item,
                market
            ).toUpperCase();

        const q =
            byCode.get(
                symbol
            ) ||
            byCode.get(
                item.code.toUpperCase()
            );

        const scored =
            quoteScore(
                q || {}
            );

        if (
            q &&
            scored &&
            shouldDeepAnalyze(
                scored,
                market
            )
        ) {

            candidates.push({

                item,

                q,

                scored

            });
        }
    }

    // ========================================================
    // ترتيب المرشحين
    // ========================================================

    candidates.sort(
        (a, b) =>
            b.scored.score -
            a.scored.score
    );

    const selected =
        candidates.slice(
            0,
            DEEP_CANDIDATES_PER_MARKET
        );

    let alerts = 0;

    console.log(
        `🔎 ${market}: ${rawQuotes.length} quotes كاملة | ` +
        `${candidates.length} مرشح | ` +
        `تحليل عميق ${selected.length}`
    );

    // ========================================================
    // 🔬 التحليل العميق
    // ========================================================

    for (
        const c of selected
    ) {

        try {

            const symbol =
                fullSymbol(
                    c.item,
                    market
                );

            const candles =
                await getIntraday(
                    symbol
                );

            const analysis =
                deepAnalyze(
                    candles,
                    c.scored
                );

            if (
                !analysis ||
                !analysis.atr
            ) {

                continue;
            }

            // ==================================================
            // 🔔 فقط الإشارات القوية
            // ==================================================

            const sendable =
                analysis.signal ===
                    "شراء قوي 🟢" ||
                analysis.signal ===
                    "بيع قوي 🔴";

            if (!sendable)
                continue;

            // ==================================================
            // منع التكرار
            // ==================================================

            const key =
                alertKey(
                    market,
                    c.item.code,
                    analysis
                );

            if (
                lastAlert.get(
                    `${market}:${c.item.code}`
                ) === key
            ) {

                continue;
            }

            lastAlert.set(
                `${market}:${c.item.code}`,
                key
            );

            // ==================================================
            // 📰 الأخبار
            // ==================================================

            const news =
                await getNews(
                    symbol
                );

            // ==================================================
            // 📲 Telegram
            // ==================================================

            if (chatId) {

                await send(
                    bot,
                    chatId,

                    signalMessage(
                        market,
                        c.item,
                        c.scored,
                        analysis,
                        news
                    )
                );

                alerts++;
            }

        } catch (e) {

            console.error(
                `❌ ${market} ${c.item.code}: ${e.message}`
            );
        }

        await sleep(200);
    }

    return {

        quotes:
            rawQuotes.length,

        candidates:
            candidates.length,

        alerts

    };
}

// ============================================================
// 🚀 دورة الفحص الكاملة
// ============================================================

async function fullScanCycle() {

    if (
        scanRunning
    ) {

        console.log(
            "⏭️ توجد دورة فحص سابقة ما زالت تعمل — تم تجاوز الدورة الجديدة"
        );

        return;
    }

    scanRunning = true;

    const started =
        Date.now();

    console.log(
        `\n🚀 بدء فحص السوق كامل — ${new Date().toLocaleString("ar-SA")}`
    );

    try {

        // ====================================================
        // تحميل القوائم إذا لم تكن موجودة
        // ====================================================

        if (
            !universes.tasi.length ||
            !universes.us.length ||
            !universes.crypto.length
        ) {

            await loadUniverses();
        }

        const results = {};

        // ====================================================
        // 🇸🇦 TASI
        // ====================================================

        results.tasi =
            await scanMarket(
                "TASI",
                universes.tasi,
                "tasi"
            );

        // ====================================================
        // 🇺🇸 NASDAQ
        // ====================================================

        results.us =
            await scanMarket(
                "NASDAQ",
                universes.us,
                "us"
            );

        // ====================================================
        // 🪙 CRYPTO
        // ====================================================

        results.crypto =
            await scanMarket(
                "CRYPTO",
                universes.crypto,
                "crypto"
            );

        console.log(
            `✅ اكتمل فحص السوق كامل في ` +
            `${(
                (Date.now() - started) /
                1000
            ).toFixed(1)}s`
        );

        console.log(
            results
        );

    } catch (e) {

        console.error(
            `❌ خطأ دورة السوق: ${e.message}`
        );

    } finally {

        scanRunning =
            false;
    }
}

// ============================================================
// ▶️ تشغيل النظام
// ============================================================

async function start() {

    console.log(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    );

    console.log(
        "💀🚀 AI PRO MAX — FULL MARKET ENGINE"
    );

    console.log(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    );

    console.log(
        EODHD_API_KEY
            ? "✅ EODHD_API_KEY موجود"
            : "❌ EODHD_API_KEY غير موجود"
    );

    console.log(
        TOKENS.tasi
            ? "✅ TASI Telegram token موجود"
            : "❌ TASI Telegram token غير موجود"
    );

    console.log(
        TOKENS.us
            ? "✅ US Telegram token موجود"
            : "❌ US Telegram token غير موجود"
    );

    console.log(
        TOKENS.crypto
            ? "✅ CRYPTO Telegram token موجود"
            : "❌ CRYPTO Telegram token غير موجود"
    );

    // ========================================================
    // 📋 تحميل الأسواق
    // ========================================================

    await loadUniverses();

    // ========================================================
    // 🚀 أول فحص بعد 5 ثواني
    // ========================================================

    setTimeout(
        () => {

            fullScanCycle()
                .catch(
                    e =>
                        console.error(e)
                );

        },
        5000
    );

    // ========================================================
    // 🔄 فحص تلقائي كل دقيقتين
    // ========================================================

    setInterval(
        () => {

            fullScanCycle()
                .catch(
                    e =>
                        console.error(e)
                );

        },
        SCAN_MINUTES *
        60 *
        1000
    );

    // ========================================================
    // 🔄 تحديث قوائم الأسهم كل ساعة
    // ========================================================

    setInterval(
        () => {

            loadUniverses()
                .catch(
                    e =>
                        console.error(
                            `❌ تحديث القوائم: ${e.message}`
                        )
                );

        },
        60 *
        60 *
        1000
    );

    console.log(
        `⏱️ الفحص التلقائي مضبوط على كل ${SCAN_MINUTES} دقائق`
    );
}

// ============================================================
// 🟢 START
// ============================================================

start()
    .catch(
        e =>
            console.error(
                `❌ فشل النظام: ${e.message}`
            )
    );