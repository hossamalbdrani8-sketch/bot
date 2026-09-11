
"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// 🤖 AI PRO MAX 💀🚀
// 🇸🇦 TASI + 🇺🇸 NASDAQ + 🪙 CRYPTO
// ⏱️ فحص كل دقيقتين
// ============================================================


// ============================================================
// 🔐 TELEGRAM
// ============================================================

const TELEGRAM_TOKEN =
    process.env.TELEGRAM_TOKEN ||
    process.env.TELEGRAM_BOT_TOKEN ||
    process.env.BOT_TOKEN ||
    "";

const TELEGRAM_CHAT_ID =
    process.env.TELEGRAM_CHAT_ID ||
    process.env.CHAT_ID ||
    "";


// ============================================================
// 🔑 EODHD
// ============================================================

const EODHD_TOKEN =
    process.env.EODHD_TOKEN ||
    process.env.EODHD_API_KEY ||
    process.env.EODHD_API_TOKEN ||
    process.env.API_TOKEN ||
    "";


// ============================================================
// 🇸🇦 TASI CONFIG
// ============================================================

const TASI_CONFIG =
    process.env.TASI_CONFIG ||
    process.env.TASI_API ||
    process.env.TASI_TOKEN ||
    "";


// ============================================================
// 🇺🇸 US CONFIG
// ============================================================

const US_CONFIG =
    process.env.US_CONFIG ||
    process.env.US_API ||
    process.env.US_TOKEN ||
    "";


// ============================================================
// 🪙 CRYPTO CONFIG
// ============================================================

const CRYPTO_CONFIG =
    process.env.CRYPTO_CONFIG ||
    process.env.CRYPTO_API ||
    process.env.CRYPTO_TOKEN ||
    "";


// ============================================================
// 🌐 PORT
// ============================================================

const PORT =
    Number(process.env.PORT || 3000);


// ============================================================
// ⚙️ الإعدادات
// ============================================================

// ⏱️ الفحص كل دقيقتين
const SCAN_INTERVAL =
    2 * 60 * 1000;

// 🇺🇸 أقل سعر أمريكي
const MIN_US_PRICE = 0.20;

// تحديث قوائم الأسواق
const SYMBOL_LIST_REFRESH =
    6 * 60 * 60 * 1000;

// تحديث بيانات TASI
const TASI_REFRESH =
    15 * 60 * 1000;

// تحديث بيانات Crypto
const CRYPTO_REFRESH =
    15 * 60 * 1000;

// تحديث التاريخ الفني
const HISTORY_REFRESH =
    30 * 60 * 1000;


// ============================================================
// 🧠 الذاكرة
// ============================================================

let bot = null;

const subscribers =
    new Set();

let running = false;

let lastScan = {
    tasi: 0,
    us: 0,
    crypto: 0
};


// ============================================================
// 📦 CACHE
// ============================================================

const cache = {

    nasdaqSymbols: new Set(),

    nasdaqSymbolsUpdated: 0,

    tasiRows: [],

    tasiUpdated: 0,

    cryptoRows: [],

    cryptoUpdated: 0,

    usQuotes: [],

    usQuotesUpdated: 0,

    history: new Map()
};


// ============================================================
// 🛑 TELEGRAM
// ============================================================

if (!TELEGRAM_TOKEN) {

    console.error(
        "❌ TELEGRAM_TOKEN غير موجود"
    );

} else {

    try {

        bot =
            new TelegramBot(
                TELEGRAM_TOKEN,
                {
                    polling: true
                }
            );

        console.log(
            "✅ Telegram Bot يعمل"
        );

    } catch (error) {

        console.error(
            "❌ خطأ تشغيل Telegram:",
            error.message
        );
    }
}


// ============================================================
// 🔑 EODHD CHECK
// ============================================================

if (!EODHD_TOKEN) {

    console.error(
        "❌ EODHD Token غير موجود"
    );

} else {

    console.log(
        "✅ موجود رمز EODHD"
    );
}


// ============================================================
// 📱 START
// ============================================================

if (bot) {

    bot.onText(
        /^\/start$/,
        async (msg) => {

            const chatId =
                String(msg.chat.id);

            subscribers.add(chatId);

            console.log(
                `✅ تمت إضافة Telegram Chat: ${chatId}`
            );

            await bot.sendMessage(
                chatId,
                [
                    "🤖 AI PRO MAX 💀🚀",
                    "",
                    "✅ البوت يعمل الآن",
                    "",
                    "🇸🇦 تاسي: جاهز",
                    "🇺🇸 NASDAQ: جاهز",
                    "🪙 العملات الرقمية: جاهزة",
                    "",
                    "⚡ الفحص تلقائي",
                    "⏱️ كل دقيقتين",
                    "",
                    "لا تحتاج إلى تشغيل الفحص يدويًا."
                ].join("\n")
            );
        }
    );


    bot.on(
        "polling_error",
        (error) => {

            console.error(
                "❌ Telegram Polling:",
                error.message
            );
        }
    );
}


// ============================================================
// 🌐 EODHD REQUEST
// ============================================================

async function eodhd(
    path,
    params = {}
) {

    if (!EODHD_TOKEN) {

        throw new Error(
            "EODHD_TOKEN غير موجود"
        );
    }

    const query =
        new URLSearchParams();

    query.set(
        "api_token",
        EODHD_TOKEN
    );

    query.set(
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

            query.set(
                key,
                String(value)
            );
        }
    }

    const url =
        `https://eodhd.com/api${path}?${query.toString()}`;

    const response =
        await fetch(url);

    const body =
        await response.text();

    if (!response.ok) {

        let message =
            body;

        try {

            const json =
                JSON.parse(body);

            message =
                json.message ||
                json.error ||
                body;

        } catch (_) {}

        throw new Error(
            `EODHD HTTP ${response.status} - ${String(message).slice(0, 250)}`
        );
    }

    try {

        return JSON.parse(body);

    } catch (_) {

        throw new Error(
            "EODHD أرسل بيانات غير JSON"
        );
    }
}


// ============================================================
// 📊 EMA
// ============================================================

function ema(
    values,
    period
) {

    if (
        !Array.isArray(values) ||
        values.length < period
    ) {

        return null;
    }

    const multiplier =
        2 / (period + 1);

    let result = 0;

    for (
        let i = 0;
        i < period;
        i++
    ) {

        result +=
            Number(values[i]) || 0;
    }

    result /=
        period;

    for (
        let i = period;
        i < values.length;
        i++
    ) {

        const value =
            Number(values[i]) || 0;

        result =
            (
                (value - result) *
                multiplier
            ) +
            result;
    }

    return result;
}


// ============================================================
// 📏 ATR14
// ============================================================

function calculateATR(
    candles,
    period = 14
) {

    if (
        !candles ||
        candles.length <
        period + 1
    ) {

        return null;
    }

    const tr = [];

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

        if (
            !Number.isFinite(high) ||
            !Number.isFinite(low) ||
            !Number.isFinite(previousClose)
        ) {

            continue;
        }

        const r1 =
            high - low;

        const r2 =
            Math.abs(
                high - previousClose
            );

        const r3 =
            Math.abs(
                low - previousClose
            );

        tr.push(
            Math.max(
                r1,
                r2,
                r3
            )
        );
    }

    if (
        tr.length < period
    ) {

        return null;
    }

    let atr = 0;

    for (
        let i = 0;
        i < period;
        i++
    ) {

        atr += tr[i];
    }

    atr /=
        period;

    for (
        let i = period;
        i < tr.length;
        i++
    ) {

        atr =
            (
                atr * (period - 1) +
                tr[i]
            ) / period;
    }

    return atr;
}


// ============================================================
// 🎯 أهداف ATR
// ============================================================

function calculateTargets(
    price,
    atr
) {

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

    return multipliers.map(
        (m, index) => ({

            name:
                `TP${index + 1}`,

            price:
                price + atr * m,

            distance:
                atr * m
        })
    );
}


// ============================================================
// 🟢🔴 SUPPORT / RESISTANCE
// ============================================================

function supportResistance(
    candles,
    lookback = 30
) {

    if (
        !candles ||
        candles.length < 5
    ) {

        return {
            support: null,
            resistance: null
        };
    }

    const data =
        candles.slice(-lookback);

    const lows =
        data
            .map(
                x => Number(x.low)
            )
            .filter(
                Number.isFinite
            );

    const highs =
        data
            .map(
                x => Number(x.high)
            )
            .filter(
                Number.isFinite
            );

    if (
        !lows.length ||
        !highs.length
    ) {

        return {
            support: null,
            resistance: null
        };
    }

    return {

        support:
            Math.min(...lows),

        resistance:
            Math.max(...highs)
    };
}


// ============================================================
// 💧 LIQUIDITY
// ============================================================

function liquidityStrength(
    candles
) {

    if (
        !candles ||
        candles.length < 11
    ) {

        return 0;
    }

    const volumes =
        candles
            .map(
                x => Number(x.volume)
            )
            .filter(
                Number.isFinite
            );

    if (
        volumes.length < 11
    ) {

        return 0;
    }

    const latest =
        volumes[
            volumes.length - 1
        ];

    const previous =
        volumes.slice(
            -11,
            -1
        );

    const average =
        previous.reduce(
            (a, b) => a + b,
            0
        ) /
        previous.length;

    if (
        average <= 0
    ) {

        return 0;
    }

    return (
        latest /
        average
    );
}


// ============================================================
// 🧠 التحليل الفني
// ============================================================

function analyze(
    symbol,
    candles,
    market,
    livePrice = null,
    changePercent = null
) {

    if (
        !candles ||
        candles.length < 60
    ) {

        return null;
    }

    const closes =
        candles
            .map(
                x => Number(x.close)
            )
            .filter(
                Number.isFinite
            );

    if (
        closes.length < 60
    ) {

        return null;
    }

    const historicalPrice =
        closes[
            closes.length - 1
        ];

    const price =
        Number.isFinite(livePrice) &&
        livePrice > 0
            ? livePrice
            : historicalPrice;

    const ema10 =
        ema(
            closes,
            10
        );

    const ema50 =
        ema(
            closes,
            50
        );

    const ema200 =
        ema(
            closes,
            200
        );

    const atr =
        calculateATR(
            candles,
            14
        );

    const sr =
        supportResistance(
            candles
        );

    const liquidity =
        liquidityStrength(
            candles
        );

    let signal =
        "محايد";

    if (
        ema10 &&
        ema50 &&
        price > ema10 &&
        ema10 > ema50
    ) {

        signal =
            "شراء قوي";

    } else if (
        ema10 &&
        price > ema10
    ) {

        signal =
            "شراء";
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

        emaFast:
            ema10,

        ema50,

        ema200,

        atr,

        support:
            sr.support,

        resistance:
            sr.resistance,

        liquidity,

        changePercent,

        targets
    };
}


// ============================================================
// 📚 التاريخ الفني
// ============================================================

async function getHistory(
    symbol
) {

    const old =
        cache.history.get(symbol);

    if (
        old &&
        Date.now() - old.time <
        HISTORY_REFRESH
    ) {

        return old.data;
    }

    try {

        const data =
            await eodhd(
                `/eod/${encodeURIComponent(symbol)}`,
                {
                    order: "a",
                    period: "d",
                    from: "2025-01-01"
                }
            );

        if (
            Array.isArray(data)
        ) {

            cache.history.set(
                symbol,
                {
                    time:
                        Date.now(),

                    data
                }
            );

            return data;
        }

    } catch (error) {

        console.log(
            `⚠️ التاريخ ${symbol}: ${error.message}`
        );
    }

    return null;
}


// ============================================================
// 🇺🇸 قائمة NASDAQ
// ============================================================

async function loadNASDAQSymbols() {

    if (
        cache.nasdaqSymbols.size &&
        Date.now() -
            cache.nasdaqSymbolsUpdated <
            SYMBOL_LIST_REFRESH
    ) {

        return;
    }

    console.log(
        "📚 تحديث قائمة NASDAQ..."
    );

    const list =
        await eodhd(
            "/exchange-symbol-list/US"
        );

    if (
        !Array.isArray(list)
    ) {

        throw new Error(
            "قائمة US غير صحيحة"
        );
    }

    const symbols =
        new Set();

    for (
        const item of list
    ) {

        const code =
            item.Code ||
            item.code ||
            item.Symbol ||
            item.symbol;

        const exchange =
            String(
                item.Exchange ||
                item.exchange ||
                item.SubExchange ||
                item.sub_exchange ||
                ""
            ).toUpperCase();

        if (
            code &&
            exchange === "NASDAQ"
        ) {

            symbols.add(
                String(code)
                    .toUpperCase()
            );
        }
    }

    cache.nasdaqSymbols =
        symbols;

    cache.nasdaqSymbolsUpdated =
        Date.now();

    console.log(
        `🇺🇸 NASDAQ: ${symbols.size} سهم`
    );
}


// ============================================================
// 🇺🇸 BULK LIVE US
// ============================================================

async function loadUSLive() {

    const data =
        await eodhd(
            "/real-time/AAPL.US",
            {
                ex: "US"
            }
        );

    if (
        !Array.isArray(data)
    ) {

        throw new Error(
            "Bulk US لم يرجع قائمة"
        );
    }

    cache.usQuotes =
        data;

    cache.usQuotesUpdated =
        Date.now();

    return data;
}


// ============================================================
// 🇸🇦 BULK TASI
// ============================================================

async function loadTASI() {

    if (
        cache.tasiRows.length &&
        Date.now() -
            cache.tasiUpdated <
            TASI_REFRESH
    ) {

        return cache.tasiRows;
    }

    console.log(
        "🇸🇦 تحديث بيانات تاسي..."
    );

    const data =
        await eodhd(
            "/eod-bulk-last-day/SA.TADAWUL",
            {
                filter:
                    "extended"
            }
        );

    if (
        !Array.isArray(data)
    ) {

        throw new Error(
            "بيانات تاسي غير صحيحة"
        );
    }

    cache.tasiRows =
        data;

    cache.tasiUpdated =
        Date.now();

    console.log(
        `🇸🇦 تاسي: ${data.length} سهم`
    );

    return data;
}


// ============================================================
// 🪙 BULK CRYPTO
// ============================================================

async function loadCrypto() {

    if (
        cache.cryptoRows.length &&
        Date.now() -
            cache.cryptoUpdated <
            CRYPTO_REFRESH
    ) {

        return cache.cryptoRows;
    }

    console.log(
        "🪙 تحديث بيانات العملات..."
    );

    const data =
        await eodhd(
            "/eod-bulk-last-day/CC"
        );

    if (
        !Array.isArray(data)
    ) {

        throw new Error(
            "بيانات العملات غير صحيحة"
        );
    }

    cache.cryptoRows =
        data;

    cache.cryptoUpdated =
        Date.now();

    console.log(
        `🪙 العملات: ${data.length}`
    );

    return data;
}


// ============================================================
// 🇺🇸 فحص NASDAQ
// ============================================================

async function scanUS() {

    console.log(
        "🇺🇸 بدء فحص NASDAQ..."
    );

    lastScan.us =
        Date.now();

    await loadNASDAQSymbols();

    const quotes =
        await loadUSLive();

    const candidates = [];

    for (
        const q of quotes
    ) {

        const rawCode =
            q.code ||
            q.Code ||
            "";

        const code =
            String(rawCode)
                .replace(
                    /\.US$/i,
                    ""
                )
                .toUpperCase();

        if (
            !cache.nasdaqSymbols.has(code)
        ) {

            continue;
        }

        const price =
            Number(q.close);

        if (
            !Number.isFinite(price) ||
            price < MIN_US_PRICE
        ) {

            continue;
        }

        const change =
            Number(
                q.change_p
            );

        candidates.push({

            symbol:
                `${code}.US`,

            price,

            change:

                Number.isFinite(change)
                    ? change
                    : 0,

            volume:
                Number(q.volume) || 0
        });
    }


    // ========================================================
    // ترتيب أولي
    // ========================================================

    candidates.sort(
        (a, b) =>
            (
                Math.abs(b.change) +
                Math.log10(
                    Math.max(
                        b.volume,
                        1
                    )
                ) / 10
            ) -
            (
                Math.abs(a.change) +
                Math.log10(
                    Math.max(
                        a.volume,
                        1
                    )
                ) / 10
            )
    );


    // أفضل 10 فقط للتحليل التاريخي
    const selected =
        candidates.slice(
            0,
            10
        );

    const results = [];

    for (
        const item of selected
    ) {

        try {

            const candles =
                await getHistory(
                    item.symbol
                );

            const analysis =
                analyze(
                    item.symbol,
                    candles,
                    "NASDAQ",
                    item.price,
                    item.change
                );

            if (
                analysis &&
                (
                    analysis.signal ===
                        "شراء قوي" ||
                    analysis.signal ===
                        "شراء"
                )
            ) {

                results.push(
                    analysis
                );
            }

        } catch (error) {

            console.log(
                `⚠️ NASDAQ ${item.symbol}: ${error.message}`
            );
        }
    }

    console.log(
        `🇺🇸 NASDAQ: ${results.length} إشارة`
    );

    return results;
}


// ============================================================
// 🇸🇦 فحص تاسي
// ============================================================

async function scanTASI() {

    console.log(
        "🇸🇦 بدء فحص تاسي..."
    );

    lastScan.tasi =
        Date.now();

    const rows =
        await loadTASI();

    const candidates =
        rows
            .map(
                row => {

                    const code =
                        row.code ||
                        row.Code ||
                        "";

                    const close =
                        Number(
                            row.close
                        );

                    const change =
                        Number(
                            row.change_p
                        );

                    const volume =
                        Number(
                            row.volume
                        ) || 0;

                    return {

                        symbol:
                            String(code)
                                .includes(".")
                                ? String(code)
                                : `${code}.SR`,

                        price:
                            close,

                        change:
                            Number.isFinite(change)
                                ? change
                                : 0,

                        volume
                    };
                }
            )
            .filter(
                x =>
                    Number.isFinite(
                        x.price
                    ) &&
                    x.price > 0
            )
            .sort(
                (a, b) =>
                    Math.abs(b.change) -
                    Math.abs(a.change)
            )
            .slice(
                0,
                10
            );

    const results = [];

    for (
        const item of candidates
    ) {

        try {

            const candles =
                await getHistory(
                    item.symbol
                );

            const analysis =
                analyze(
                    item.symbol,
                    candles,
                    "TASI",
                    item.price,
                    item.change
                );

            if (
                analysis &&
                (
                    analysis.signal ===
                        "شراء قوي" ||
                    analysis.signal ===
                        "شراء"
                )
            ) {

                results.push(
                    analysis
                );
            }

        } catch (error) {

            console.log(
                `⚠️ TASI ${item.symbol}: ${error.message}`
            );
        }
    }

    console.log(
        `🇸🇦 تاسي: ${results.length} إشارة`
    );

    return results;
}


// ============================================================
// 🪙 فحص العملات
// ============================================================

async function scanCrypto() {

    console.log(
        "🪙 بدء فحص العملات الرقمية..."
    );

    lastScan.crypto =
        Date.now();

    const rows =
        await loadCrypto();

    const candidates =
        rows
            .map(
                row => {

                    const code =
                        row.code ||
                        row.Code ||
                        "";

                    const close =
                        Number(
                            row.close
                        );

                    const change =
                        Number(
                            row.change_p
                        );

                    const volume =
                        Number(
                            row.volume
                        ) || 0;

                    return {

                        symbol:
                            String(code)
                                .includes(".")
                                ? String(code)
                                : `${code}.CC`,

                        price:
                            close,

                        change:
                            Number.isFinite(change)
                                ? change
                                : 0,

                        volume
                    };
                }
            )
            .filter(
                x =>
                    Number.isFinite(
                        x.price
                    ) &&
                    x.price > 0
            )
            .sort(
                (a, b) =>
                    Math.abs(b.change) -
                    Math.abs(a.change)
            )
            .slice(
                0,
                10
            );

    const results = [];

    for (
        const item of candidates
    ) {

        try {

            const candles =
                await getHistory(
                    item.symbol
                );

            const analysis =
                analyze(
                    item.symbol,
                    candles,
                    "CRYPTO",
                    item.price,
                    item.change
                );

            if (
                analysis &&
                (
                    analysis.signal ===
                        "شراء قوي" ||
                    analysis.signal ===
                        "شراء"
                )
            ) {

                results.push(
                    analysis
                );
            }

        } catch (error) {

            console.log(
                `⚠️ CRYPTO ${item.symbol}: ${error.message}`
            );
        }
    }

    console.log(
        `🪙 العملات: ${results.length} إشارة`
    );

    return results;
}


// ============================================================
// 📩 رسالة الإشارة
// ============================================================

function formatSignal(
    x
) {

    let text = "";

    text +=
        "🤖 AI PRO MAX 💀🚀\n";

    text +=
        "━━━━━━━━━━━━━━━━━━\n";

    text +=
        `📊 السوق: ${x.market}\n`;

    text +=
        `🔹 الرمز: ${x.symbol}\n`;

    text +=
        `💰 السعر: ${Number(x.price).toFixed(4)}\n`;

    text +=
        `🚦 الإشارة: ${x.signal}\n`;

    if (
        Number.isFinite(
            x.changePercent
        )
    ) {

        text +=
            `📊 التغير: ${x.changePercent.toFixed(2)}%\n`;
    }

    if (
        Number.isFinite(
            x.emaFast
        )
    ) {

        text +=
            `📈 EMA10: ${x.emaFast.toFixed(4)}\n`;
    }

    if (
        Number.isFinite(
            x.ema50
        )
    ) {

        text +=
            `📈 EMA50: ${x.ema50.toFixed(4)}\n`;
    }

    if (
        Number.isFinite(
            x.ema200
        )
    ) {

        text +=
            `📈 EMA200: ${x.ema200.toFixed(4)}\n`;
    }

    if (
        Number.isFinite(
            x.atr
        )
    ) {

        text +=
            `📏 ATR14: ${x.atr.toFixed(4)}\n`;
    }

    if (
        Number.isFinite(
            x.support
        )
    ) {

        text +=
            `🟢 الدعم: ${x.support.toFixed(4)}\n`;
    }

    if (
        Number.isFinite(
            x.resistance
        )
    ) {

        text +=
            `🔴 المقاومة: ${x.resistance.toFixed(4)}\n`;
    }

    if (
        Number.isFinite(
            x.liquidity
        )
    ) {

        text +=
            `💧 قوة السيولة: ${x.liquidity.toFixed(2)}x\n`;
    }

    if (
        x.targets &&
        x.targets.length
    ) {

        text +=
            "\n🎯 أهداف ATR:\n";

        for (
            const target
            of x.targets
        ) {

            text +=
                `${target.name}: ${target.price.toFixed(4)}\n`;
        }
    }

    text +=
        "\n━━━━━━━━━━━━━━━━━━\n";

    text +=
        "⚡ فحص تلقائي كل دقيقتين";

    return text;
}


// ============================================================
// 📤 إرسال Telegram
// ============================================================

async function sendResults(
    results
) {

    if (!bot) {
        return;
    }

    const ids =
        new Set(
            subscribers
        );

    if (
        TELEGRAM_CHAT_ID
    ) {

        ids.add(
            String(
                TELEGRAM_CHAT_ID
            )
        );
    }

    if (!ids.size) {

        console.log(
            "ℹ️ لا يوجد Telegram Chat مسجل"
        );

        return;
    }

    const selected =
        results
            .sort(
                (a, b) =>
                    b.liquidity -
                    a.liquidity
            )
            .slice(
                0,
                20
            );

    for (
        const item
        of selected
    ) {

        const message =
            formatSignal(
                item
            );

        for (
            const chatId
            of ids
        ) {

            try {

                await bot.sendMessage(
                    chatId,
                    message
                );

            } catch (error) {

                console.error(
                    "❌ Telegram:",
                    error.message
                );
            }
        }
    }
}


// ============================================================
// 🚀 دورة الفحص
// ============================================================

async function fullScan() {

    if (running) {

        console.log(
            "⏳ يوجد فحص سابق يعمل..."
        );

        return;
    }

    running = true;

    console.log(
        "\n🚀 AI PRO MAX — بدء دورة فحص جديدة"
    );

    try {

        const allResults = [];


        // 🇸🇦 TASI

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


        // 🇺🇸 NASDAQ

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


        // 🪙 CRYPTO

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

        running =
            false;
    }
}


// ============================================================
// 🌐 RAILWAY SERVER
// ============================================================

const app =
    express();


app.get(
    "/",
    (req, res) => {

        res.json({

            bot:
                "AI PRO MAX 💀🚀",

            status:
                "online",

            telegram:
                !!bot,

            eodhd:
                !!EODHD_TOKEN,

            automatic:
                true,

            scanEveryMinutes:
                2,

            markets: {

                tasi:
                    !!TASI_CONFIG ||
                    !!EODHD_TOKEN,

                nasdaq:
                    !!US_CONFIG ||
                    !!EODHD_TOKEN,

                crypto:
                    !!CRYPTO_CONFIG ||
                    !!EODHD_TOKEN
            },

            cache: {

                nasdaq:
                    cache.nasdaqSymbols.size,

                tasi:
                    cache.tasiRows.length,

                crypto:
                    cache.cryptoRows.length
            },

            lastScan
        });
    }
);


app.get(
    "/health",
    (req, res) => {

        res
            .status(200)
            .send(
                "AI PRO MAX ONLINE"
            );
    }
);


app.listen(
    PORT,
    () => {

        console.log(
            `🌐 الخادم يعمل على المنفذ ${PORT}`
        );

        console.log(
            "🇸🇦 TASI: جاهز"
        );

        console.log(
            "🇺🇸 NASDAQ: جاهز"
        );

        console.log(
            "🪙 CRYPTO: جاهز"
        );

        console.log(
            "⏱️ الفحص التلقائي: كل دقيقتين"
        );

        setTimeout(
            fullScan,
            10000
        );

        setInterval(
            fullScan,
            SCAN_INTERVAL
        );
    }
);