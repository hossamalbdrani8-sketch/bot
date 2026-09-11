
"use strict";

/*
============================================================
💀🚀 AI PRO MAX — AUTONOMOUS MARKET SCANNER
Node.js 18+
مصدر البيانات الوحيد: EODHD
Telegram: TASI + US + CRYPTO
============================================================
*/

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const fs = require("fs");
const path = require("path");

/* =========================================================
   ⚙️ متغيرات Railway — لا تغيّر أسماءها
========================================================= */

const TASI_TOKEN = String(process.env.TASI_CONFIG || "").trim();
const US_TOKEN = String(process.env.US_CONFIG || "").trim();
const CRYPTO_TOKEN = String(process.env.CRYPTO_CONFIG || "").trim();
const EODHD_KEY = String(process.env.EODHD_API_KEY || "").trim();

const PORT = Number(process.env.PORT || 3000);

const SCAN_INTERVAL = 2 * 60 * 1000;

const UNIVERSE_CACHE_TIME = 6 * 60 * 60 * 1000;

const DEEP_CACHE_TIME = 10 * 60 * 1000;

const ALERT_COOLDOWN = 20 * 60 * 1000;

const STATE_FILE = path.join(__dirname, "chat_ids.json");

/* =========================================================
   💾 حالة البوت
========================================================= */

let state = {
    TASI: [],
    US: [],
    CRYPTO: []
};

try {
    if (fs.existsSync(STATE_FILE)) {
        const saved = JSON.parse(
            fs.readFileSync(STATE_FILE, "utf8")
        );

        if (saved && typeof saved === "object") {
            state = saved;
        }
    }
} catch (error) {
    console.log(
        "⚠️ تعذر قراءة chat_ids.json:",
        error.message
    );
}

for (const market of ["TASI", "US", "CRYPTO"]) {
    if (!Array.isArray(state[market])) {
        state[market] = [];
    }
}

function saveState() {
    try {
        fs.writeFileSync(
            STATE_FILE,
            JSON.stringify(state, null, 2),
            "utf8"
        );
    } catch (error) {
        console.log(
            "⚠️ تعذر حفظ chat_ids:",
            error.message
        );
    }
}

/* =========================================================
   📝 LOG
========================================================= */

function log(message) {
    console.log(
        `${new Date().toISOString()} | ${message}`
    );
}

const errorMemory = new Map();

function logErrorOnce(
    key,
    message,
    cooldown = 5 * 60 * 1000
) {
    const now = Date.now();

    const last = errorMemory.get(key) || 0;

    if (now - last >= cooldown) {
        errorMemory.set(key, now);

        console.log(
            `${new Date().toISOString()} | ${message}`
        );
    }
}

/* =========================================================
   🔐 فحص الإعدادات
========================================================= */

function checkConfig() {

    const missing = [];

    if (!TASI_TOKEN) {
        missing.push("TASI_CONFIG");
    }

    if (!US_TOKEN) {
        missing.push("US_CONFIG");
    }

    if (!CRYPTO_TOKEN) {
        missing.push("CRYPTO_CONFIG");
    }

    if (!EODHD_KEY) {
        missing.push("EODHD_API_KEY");
    }

    if (missing.length) {
        throw new Error(
            `متغيرات Railway ناقصة: ${missing.join(", ")}`
        );
    }

    log("✅ TASI_CONFIG موجود");

    log("✅ US_CONFIG موجود");

    log("✅ CRYPTO_CONFIG موجود");

    log("✅ EODHD_API_KEY موجود");
}

/* =========================================================
   🌐 EODHD REQUEST ENGINE
========================================================= */

if (typeof fetch !== "function") {
    throw new Error(
        "❌ Node.js 18 أو أحدث مطلوب."
    );
}

function makeEODHDUrl(
    endpoint,
    params = {}
) {

    const url = new URL(
        `https://eodhd.com/api/${endpoint.replace(/^\/+/, "")}`
    );

    url.searchParams.set(
        "api_token",
        EODHD_KEY
    );

    url.searchParams.set(
        "fmt",
        "json"
    );

    for (const [key, value] of Object.entries(params)) {

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

    return url.toString();
}

async function eodhd(
    endpoint,
    params = {},
    timeout = 30000
) {

    const controller =
        new AbortController();

    const timer = setTimeout(
        () => controller.abort(),
        timeout
    );

    let response;

    let text = "";

    try {

        response = await fetch(
            makeEODHDUrl(
                endpoint,
                params
            ),
            {
                method: "GET",

                headers: {
                    "Accept": "application/json",
                    "User-Agent": "AI-PRO-MAX/4.0"
                },

                signal: controller.signal
            }
        );

        text = await response.text();

    } catch (error) {

        if (
            error.name === "AbortError"
        ) {

            throw new Error(
                "EODHD NETWORK: TIMEOUT"
            );

        }

        throw new Error(
            `EODHD NETWORK: ${error.message}`
        );

    } finally {

        clearTimeout(timer);
    }

    let data = null;

    try {

        data = JSON.parse(text);

    } catch (_) {

        data = null;
    }

    if (!response.ok) {

        let message = "";

        if (data && typeof data === "object") {

            message =
                data.message ||
                data.error ||
                data.detail ||
                "";

        }

        if (!message) {
            message = text.slice(0, 600);
        }

        throw new Error(
            `EODHD HTTP ${response.status}: ${message}`
        );
    }

    if (
        data &&
        typeof data === "object" &&
        !Array.isArray(data) &&
        data.error
    ) {

        throw new Error(
            `EODHD: ${data.error}`
        );
    }

    return data;
}

/* =========================================================
   🧰 HELPERS
========================================================= */

function num(
    value,
    fallback = 0
) {

    const n = Number(value);

    return Number.isFinite(n)
        ? n
        : fallback;
}

function clamp(
    value,
    min,
    max
) {

    return Math.max(
        min,
        Math.min(max, value)
    );
}

function percentage(value) {

    const n = num(value);

    return (
        `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`
    );
}

function money(
    value,
    decimals = 4
) {

    const n = num(value);

    if (!Number.isFinite(n)) {
        return "—";
    }

    if (Math.abs(n) >= 1000) {

        return n.toLocaleString(
            "en-US",
            {
                maximumFractionDigits: 2
            }
        );
    }

    return n
        .toFixed(decimals)
        .replace(/0+$/, "")
        .replace(/\.$/, "");
}

function compact(value) {

    const n = num(value);

    const abs = Math.abs(n);

    if (abs >= 1e9) {
        return `${(n / 1e9).toFixed(2)}B`;
    }

    if (abs >= 1e6) {
        return `${(n / 1e6).toFixed(2)}M`;
    }

    if (abs >= 1e3) {
        return `${(n / 1e3).toFixed(2)}K`;
    }

    return Math.round(n)
        .toLocaleString("en-US");
}

function sleep(ms) {

    return new Promise(
        resolve => setTimeout(resolve, ms)
    );
}

function chunk(
    array,
    size
) {

    const result = [];

    for (
        let i = 0;
        i < array.length;
        i += size
    ) {

        result.push(
            array.slice(
                i,
                i + size
            )
        );
    }

    return result;
}

function unique(array) {

    return [
        ...new Set(array)
    ];
}

/* =========================================================
   📈 EMA
========================================================= */

function calculateEMA(
    values,
    length
) {

    if (!values.length) {
        return [];
    }

    const multiplier =
        2 / (length + 1);

    const result =
        new Array(values.length);

    result[0] = values[0];

    for (
        let i = 1;
        i < values.length;
        i++
    ) {

        result[i] =
            values[i] * multiplier +
            result[i - 1] *
            (1 - multiplier);
    }

    return result;
}

/* =========================================================
   📟 RSI
========================================================= */

function calculateRSI(
    values,
    length = 14
) {

    if (
        values.length <
        length + 1
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

        const difference =
            values[i] -
            values[i - 1];

        gain += Math.max(
            difference,
            0
        );

        loss += Math.max(
            -difference,
            0
        );
    }

    gain /= length;

    loss /= length;

    for (
        let i = length + 1;
        i < values.length;
        i++
    ) {

        const difference =
            values[i] -
            values[i - 1];

        const currentGain =
            Math.max(
                difference,
                0
            );

        const currentLoss =
            Math.max(
                -difference,
                0
            );

        gain =
            (
                gain * (length - 1) +
                currentGain
            ) / length;

        loss =
            (
                loss * (length - 1) +
                currentLoss
            ) / length;
    }

    if (loss === 0) {
        return 100;
    }

    const rs =
        gain / loss;

    return (
        100 -
        100 / (1 + rs)
    );
}

/* =========================================================
   🔥 ATR
========================================================= */

function calculateATR(
    candles,
    length = 14
) {

    if (
        candles.length <
        length + 1
    ) {

        return 0;
    }

    const trueRanges = [];

    for (
        let i = 1;
        i < candles.length;
        i++
    ) {

        const high =
            num(candles[i].high);

        const low =
            num(candles[i].low);

        const previousClose =
            num(
                candles[i - 1].close
            );

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

        trueRanges.push(tr);
    }

    if (
        trueRanges.length <
        length
    ) {

        return 0;
    }

    let result =
        trueRanges
            .slice(0, length)
            .reduce(
                (a, b) => a + b,
                0
            ) / length;

    for (
        let i = length;
        i < trueRanges.length;
        i++
    ) {

        result =
            (
                result *
                (length - 1) +
                trueRanges[i]
            ) / length;
    }

    return result;
}

/* =========================================================
   📊 AVERAGE
========================================================= */

function average(values) {

    if (!values.length) {
        return 0;
    }

    return (
        values.reduce(
            (a, b) => a + b,
            0
        ) / values.length
    );
}

/* =========================================================
   🇸🇦 اكتشاف بورصة السعودية
========================================================= */

let saudiExchange = null;

let saudiExchangeTime = 0;

async function findSaudiExchange() {

    if (
        saudiExchange &&
        Date.now() -
        saudiExchangeTime <
        UNIVERSE_CACHE_TIME
    ) {

        return saudiExchange;
    }

    const exchanges =
        await eodhd(
            "exchanges-list/"
        );

    if (
        !Array.isArray(exchanges)
    ) {

        throw new Error(
            "EODHD لم يرجع قائمة البورصات"
        );
    }

    const matches =
        exchanges.filter(
            exchange => {

                const text = [
                    exchange.Name,
                    exchange.Code,
                    exchange.Country,
                    exchange.CountryISO2,
                    exchange.CountryISO3
                ]
                .filter(Boolean)
                .join(" ")
                .toLowerCase();

                return (
                    exchange.CountryISO2 === "SA" ||
                    exchange.CountryISO3 === "SAU" ||
                    text.includes("saudi") ||
                    text.includes("tadawul")
                );
            }
        );

    if (!matches.length) {

        throw new Error(
            "لم يتم العثور على بورصة السعودية داخل EODHD"
        );
    }

    const preferred =
        matches.find(
            x =>
                /tadawul/i.test(
                    String(x.Name || "")
                )
        ) ||
        matches.find(
            x =>
                String(
                    x.Currency || ""
                ).toUpperCase() === "SAR"
        ) ||
        matches[0];

    saudiExchange =
        String(
            preferred.Code || ""
        ).trim();

    if (!saudiExchange) {

        throw new Error(
            "تم العثور على السعودية ولكن بدون رمز بورصة"
        );
    }

    saudiExchangeTime =
        Date.now();

    log(
        `🇸🇦 بورصة السعودية المكتشفة تلقائياً: ${saudiExchange}`
    );

    return saudiExchange;
}

/* =========================================================
   🌎 UNIVERSAL UNIVERSE
========================================================= */

const universe = {

    TASI: {
        symbols: [],
        names: new Map(),
        loadedAt: 0
    },

    US: {
        symbols: [],
        names: new Map(),
        loadedAt: 0
    },

    CRYPTO: {
        symbols: [],
        names: new Map(),
        loadedAt: 0
    }
};

/* =========================================================
   📋 تحميل رموز بورصة
========================================================= */

async function getExchangeSymbols(
    exchange,
    type = null
) {

    const params = {};

    if (type) {
        params.type = type;
    }

    const data =
        await eodhd(
            `exchange-symbol-list/${encodeURIComponent(exchange)}`,
            params,
            60000
        );

    if (!Array.isArray(data)) {

        throw new Error(
            `قائمة ${exchange} غير صالحة`
        );
    }

    return data;
}

/* =========================================================
   🔧 تحويل الرمز
========================================================= */

function normalizeSymbol(
    row,
    market
) {

    const code =
        String(
            row.Code ||
            row.code ||
            ""
        ).trim();

    if (!code) {
        return null;
    }

    const name =
        String(
            row.Name ||
            row.name ||
            code
        ).trim();

    const type =
        String(
            row.Type ||
            row.type ||
            ""
        ).trim();

    let symbol = code;

    if (market === "US") {

        symbol =
            code
                .replace(/\s+/g, "")
                .toUpperCase();

    } else if (
        market === "CRYPTO"
    ) {

        symbol =
            code.toUpperCase();

        if (!symbol.includes(".")) {
            symbol += ".CC";
        }

    } else {

        const exchange =
            String(
                row.Exchange ||
                row.exchange ||
                saudiExchange ||
                ""
            ).trim();

        if (exchange) {

            symbol =
                `${code}.${exchange}`;
        }
    }

    return {
        symbol,
        code,
        name,
        type,
        exchange:
            row.Exchange ||
            row.exchange ||
            ""
    };
}

/* =========================================================
   🇸🇦 تحميل TASI
========================================================= */

async function loadTASI() {

    const exchange =
        await findSaudiExchange();

    const rows =
        await getExchangeSymbols(
            exchange,
            "common_stock"
        );

    const symbols = [];

    const names =
        new Map();

    for (const row of rows) {

        const item =
            normalizeSymbol(
                row,
                "TASI"
            );

        if (!item) {
            continue;
        }

        const type =
            item.type.toLowerCase();

        if (
            type &&
            !/common stock|preferred stock|stock/.test(type)
        ) {

            continue;
        }

        symbols.push(
            item.symbol
        );

        names.set(
            item.symbol,
            item.name
        );
    }

    universe.TASI = {

        symbols:
            unique(symbols),

        names,

        loadedAt:
            Date.now()
    };

    log(
        `🇸🇦 TASI تم تحميل ${universe.TASI.symbols.length} سهم`
    );
}

/* =========================================================
   🇺🇸 تحميل US
========================================================= */

async function loadUS() {

    const rows =
        await getExchangeSymbols(
            "US",
            "common_stock"
        );

    const symbols = [];

    const names =
        new Map();

    for (const row of rows) {

        const item =
            normalizeSymbol(
                row,
                "US"
            );

        if (!item) {
            continue;
        }

        const venue =
            String(
                row.Exchange || ""
            ).toUpperCase();

        const type =
            item.type.toLowerCase();

        if (
            venue &&
            /OTC|PINK|GREY|NMFQS/.test(
                venue
            )
        ) {

            continue;
        }

        if (
            type &&
            !/common stock|preferred stock|stock/.test(type)
        ) {

            continue;
        }

        symbols.push(
            item.symbol
        );

        names.set(
            item.symbol,
            item.name
        );
    }

    universe.US = {

        symbols:
            unique(symbols),

        names,

        loadedAt:
            Date.now()
    };

    log(
        `🇺🇸 US تم تحميل ${universe.US.symbols.length} سهم`
    );
}

/* =========================================================
   🪙 تحميل CRYPTO
========================================================= */

async function loadCRYPTO() {

    const rows =
        await getExchangeSymbols(
            "CC"
        );

    const symbols = [];

    const names =
        new Map();

    for (const row of rows) {

        const item =
            normalizeSymbol(
                row,
                "CRYPTO"
            );

        if (!item) {
            continue;
        }

        symbols.push(
            item.symbol
        );

        names.set(
            item.symbol,
            item.name
        );
    }

    universe.CRYPTO = {

        symbols:
            unique(symbols),

        names,

        loadedAt:
            Date.now()
    };

    log(
        `🪙 CRYPTO تم تحميل ${universe.CRYPTO.symbols.length} زوج`
    );
}

/* =========================================================
   🔄 التأكد من Universe
========================================================= */

async function ensureUniverse(
    market
) {

    const current =
        universe[market];

    if (
        current.symbols.length &&
        Date.now() -
        current.loadedAt <
        UNIVERSE_CACHE_TIME
    ) {

        return current.symbols;
    }

    try {

        if (market === "TASI") {
            await loadTASI();
        }

        if (market === "US") {
            await loadUS();
        }

        if (market === "CRYPTO") {
            await loadCRYPTO();
        }

        return universe[market].symbols;

    } catch (error) {

        logErrorOnce(
            `UNIVERSE_${market}_${error.message}`,
            `❌ ${market}: فشل تحميل القائمة — ${error.message}`,
            10 * 60 * 1000
        );

        return universe[market].symbols;
    }
}

/* =========================================================
   💰 QUOTE NORMALIZER
========================================================= */

function normalizeQuote(
    quote,
    market
) {

    if (
        !quote ||
        typeof quote !== "object"
    ) {

        return null;
    }

    const symbol =
        String(
            quote.code ||
            quote.Code ||
            quote.s ||
            quote.symbol ||
            quote.Symbol ||
            ""
        ).trim();

    const price =
        num(
            quote.close ??
            quote.price ??
            quote.last ??
            quote.lastTrade
        );

    if (
        !symbol ||
        price <= 0
    ) {

        return null;
    }

    const open =
        num(
            quote.open ??
            quote.Open
        );

    const high =
        num(
            quote.high ??
            quote.High
        );

    const low =
        num(
            quote.low ??
            quote.Low
        );

    const volume =
        num(
            quote.volume ??
            quote.Volume
        );

    const previousClose =
        num(
            quote.previousClose ??
            quote.prevClose ??
            quote.PreviousClose
        );

    let changeP =
        num(
            quote.change_p ??
            quote.changePercent ??
            quote.percentChange ??
            quote.ChangeP
        );

    if (
        !changeP &&
        previousClose
    ) {

        changeP =
            (
                (price -
                    previousClose) /
                previousClose
            ) * 100;
    }

    return {

        symbol:
            market === "US"
                ? symbol.toUpperCase()
                : symbol,

        price,

        open,

        high,

        low,

        volume,

        previousClose,

        changeP,

        market,

        time:
            Date.now()
    };
}

/* =========================================================
   📡 جلب الأسعار بالجملة
========================================================= */

async function getQuotes(
    symbols,
    market
) {

    if (!symbols.length) {
        return [];
    }

    const all = [];

    const batchSize =
        market === "US"
            ? 150
            : 100;

    const batches =
        chunk(
            symbols,
            batchSize
        );

    for (const batch of batches) {

        try {

            const first =
                batch[0];

            const rest =
                batch
                    .slice(1)
                    .join(",");

            const data =
                await eodhd(
                    `real-time/${encodeURIComponent(first)}`,
                    {
                        s:
                            rest || undefined
                    },
                    30000
                );

            if (Array.isArray(data)) {

                for (
                    const item of data
                ) {

                    const quote =
                        normalizeQuote(
                            item,
                            market
                        );

                    if (quote) {
                        all.push(quote);
                    }
                }

            } else if (
                data &&
                typeof data === "object"
            ) {

                const single =
                    normalizeQuote(
                        data,
                        market
                    );

                if (single) {
                    all.push(single);
                }

                for (
                    const [key, value]
                    of Object.entries(data)
                ) {

                    if (
                        value &&
                        typeof value === "object"
                    ) {

                        const quote =
                            normalizeQuote(
                                {
                                    ...value,
                                    s:
                                        value.s ||
                                        key
                                },
                                market
                            );

                        if (quote) {
                            all.push(quote);
                        }
                    }
                }
            }

            await sleep(80);

        } catch (error) {

            logErrorOnce(
                `QUOTE_${market}_${error.message}`,
                `❌ ${market}: فشل جلب الأسعار — ${error.message}`,
                10 * 60 * 1000
            );
        }
    }

    const seen =
        new Set();

    return all.filter(
        quote => {

            const key =
                `${market}:${quote.symbol}`;

            if (seen.has(key)) {
                return false;
            }

            seen.add(key);

            return true;
        }
    );
}

/* =========================================================
   🧠 CACHE للتحليل
========================================================= */

const deepCache =
    new Map();

function getDeepCache(
    symbol
) {

    const cached =
        deepCache.get(symbol);

    if (!cached) {
        return null;
    }

    if (
        Date.now() -
        cached.time >
        DEEP_CACHE_TIME
    ) {

        deepCache.delete(symbol);

        return null;
    }

    return cached.data;
}

function setDeepCache(
    symbol,
    data
) {

    deepCache.set(
        symbol,
        {
            time: Date.now(),
            data
        }
    );
}

/* =========================================================
   📊 Intraday
========================================================= */

async function getIntraday(
    symbol
) {

    const now =
        Math.floor(
            Date.now() / 1000
        );

    const from =
        now -
        2 * 24 * 60 * 60;

    return await eodhd(
        `intraday/${encodeURIComponent(symbol)}`,
        {
            interval: "5m",
            from,
            to: now
        },
        30000
    );
}

/* =========================================================
   📆 Daily
========================================================= */

async function getDaily(
    symbol
) {

    const to =
        new Date()
            .toISOString()
            .slice(0, 10);

    const from =
        new Date(
            Date.now() -
            120 * 86400000
        )
        .toISOString()
        .slice(0, 10);

    return await eodhd(
        `eod/${encodeURIComponent(symbol)}`,
        {
            from,
            to,
            order: "a"
        },
        30000
    );
}

/* =========================================================
   📰 الأخبار
========================================================= */

async function getNews(
    symbol
) {

    try {

        const data =
            await eodhd(
                "news",
                {
                    s: symbol,
                    limit: 3
                },
                20000
            );

        if (
            !Array.isArray(data) ||
            !data.length
        ) {

            return null;
        }

        const item =
            data[0];

        return {

            title:
                String(
                    item.title ||
                    item.headline ||
                    ""
                ).trim(),

            source:
                String(
                    item.source ||
                    ""
                ).trim(),

            link:
                String(
                    item.link ||
                    item.url ||
                    ""
                ).trim(),

            date:
                String(
                    item.date ||
                    ""
                ).trim()
        };

    } catch (_) {

        return null;
    }
}

/* =========================================================
   📌 دعم ومقاومة
========================================================= */

function calculateSupportResistance(
    daily
) {

    if (
        !Array.isArray(daily) ||
        daily.length < 10
    ) {

        return {
            support: 0,
            resistance: 0
        };
    }

    const rows =
        daily.slice(-40);

    const lows =
        rows
            .map(
                x => num(x.low)
            )
            .filter(
                x => x > 0
            );

    const highs =
        rows
            .map(
                x => num(x.high)
            )
            .filter(
                x => x > 0
            );

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

/* =========================================================
   📦 قوة الحجم
========================================================= */

function calculateVolumeStrength(
    candles
) {

    if (
        !Array.isArray(candles) ||
        candles.length < 10
    ) {

        return 1;
    }

    const volumes =
        candles
            .map(
                x => num(x.volume)
            )
            .filter(
                x => x > 0
            );

    if (
        volumes.length < 5
    ) {

        return 1;
    }

    const recent =
        average(
            volumes.slice(-5)
        );

    const base =
        average(
            volumes.slice(-20)
        );

    if (!base) {
        return 1;
    }

    return recent / base;
}

/* =========================================================
   🎯 8 أهداف ATR
========================================================= */

function buildTargets(
    price,
    atrValue,
    direction
) {

    const safeATR =
        Math.max(
            atrValue,
            price * 0.01
        );

    const multipliers = [
        1,
        1.5,
        2,
        2.5,
        3,
        4,
        5,
        6
    ];

    return multipliers.map(
        (multiplier, index) => {

            const distance =
                safeATR *
                multiplier;

            const target =
                direction === "BUY"
                    ? price + distance
                    : price - distance;

            const change =
                (
                    distance /
                    price
                ) * 100;

            return {

                number:
                    index + 1,

                price:
                    target,

                percentage:
                    direction === "BUY"
                        ? change
                        : -change
            };
        }
    );
}

/* =========================================================
   🧠 AI TECHNICAL ENGINE
========================================================= */

async function analyzeStock(
    quote
) {

    const cached =
        getDeepCache(
            quote.symbol
        );

    if (cached) {

        return {
            ...quote,
            ...cached
        };
    }

    let intraday = [];

    let daily = [];

    try {

        const data =
            await getIntraday(
                quote.symbol
            );

        if (
            Array.isArray(data)
        ) {

            intraday = data;
        }

    } catch (error) {

        logErrorOnce(
            `INTRADAY_${quote.symbol}_${error.message}`,
            `⚠️ Intraday ${quote.symbol}: ${error.message}`,
            30 * 60 * 1000
        );
    }

    try {

        const data =
            await getDaily(
                quote.symbol
            );

        if (
            Array.isArray(data)
        ) {

            daily = data;
        }

    } catch (error) {

        logErrorOnce(
            `DAILY_${quote.symbol}_${error.message}`,
            `⚠️ Daily ${quote.symbol}: ${error.message}`,
            30 * 60 * 1000
        );
    }

    const intradayCloses =
        intraday
            .map(
                x => num(x.close)
            )
            .filter(
                x => x > 0
            );

    const dailyCloses =
        daily
            .map(
                x => num(x.close)
            )
            .filter(
                x => x > 0
            );

    const prices =
        intradayCloses.length >= 30
            ? intradayCloses
            : dailyCloses;

    const ema8 =
        prices.length >= 8
            ? calculateEMA(
                prices,
                8
            ).at(-1)
            : quote.price;

    const ema21 =
        prices.length >= 21
            ? calculateEMA(
                prices,
                21
            ).at(-1)
            : quote.price;

    const ema50 =
        prices.length >= 50
            ? calculateEMA(
                prices,
                50
            ).at(-1)
            : quote.price;

    const rsi14 =
        prices.length >= 15
            ? calculateRSI(
                prices,
                14
            )
            : 50;

    const atr14 =
        intraday.length >= 15
            ? calculateATR(
                intraday,
                14
            )
            : daily.length >= 15
                ? calculateATR(
                    daily,
                    14
                )
                : quote.price * 0.01;

    const sr =
        calculateSupportResistance(
            daily
        );

    const volumeStrength =
        calculateVolumeStrength(
            intraday.length
                ? intraday
                : daily
        );

    const bullishTrend =
        ema8 > ema21 &&
        ema21 >= ema50;

    const bearishTrend =
        ema8 < ema21 &&
        ema21 <= ema50;

    const bullishMomentum =
        rsi14 >= 55 &&
        rsi14 <= 82;

    const bearishMomentum =
        rsi14 <= 45 &&
        rsi14 >= 18;

    let buyScore = 0;

    let sellScore = 0;

    /* EMA */
    if (bullishTrend) {
        buyScore += 30;
    }

    if (bearishTrend) {
        sellScore += 30;
    }

    /* Price momentum */
    if (quote.changeP > 0) {

        buyScore += clamp(
            quote.changeP * 2,
            0,
            15
        );
    }

    if (quote.changeP < 0) {

        sellScore += clamp(
            Math.abs(
                quote.changeP
            ) * 2,
            0,
            15
        );
    }

    /* RSI */
    if (bullishMomentum) {
        buyScore += 15;
    }

    if (bearishMomentum) {
        sellScore += 15;
    }

    /* Volume */
    if (
        volumeStrength >= 1.5
    ) {

        if (
            quote.changeP >= 0
        ) {

            buyScore += 15;

        } else {

            sellScore += 15;
        }
    }

    /* Support */
    if (
        sr.support &&
        quote.price >= sr.support
    ) {

        buyScore += 10;
    }

    /* Resistance */
    if (
        sr.resistance &&
        quote.price <=
        sr.resistance
    ) {

        sellScore += 10;
    }

    buyScore =
        clamp(
            Math.round(
                buyScore
            ),
            0,
            100
        );

    sellScore =
        clamp(
            Math.round(
                sellScore
            ),
            0,
            100
        );

    let signal =
        "WATCH";

    let score =
        Math.max(
            buyScore,
            sellScore
        );

    if (
        buyScore >= 75 &&
        buyScore >
        sellScore + 8
    ) {

        signal = "BUY";
    }

    if (
        sellScore >= 75 &&
        sellScore >
        buyScore + 8
    ) {

        signal = "SELL";
    }

    const direction =
        signal === "SELL"
            ? "SELL"
            : "BUY";

    const targets =
        buildTargets(
            quote.price,
            atr14,
            direction
        );

    const result = {

        ema8,

        ema21,

        ema50,

        rsi14,

        atr14,

        support:
            sr.support,

        resistance:
            sr.resistance,

        volumeStrength,

        buyScore,

        sellScore,

        score,

        signal,

        targets,

        trend:
            bullishTrend
                ? "صاعد قوي"
                : bearishTrend
                    ? "هابط قوي"
                    : "متذبذب"
    };

    setDeepCache(
        quote.symbol,
        result
    );

    return {
        ...quote,
        ...result
    };
}

/* =========================================================
   🚨 منع تكرار الإشارات
========================================================= */

const alertMemory =
    new Map();

function alertKey(
    market,
    symbol,
    signal
) {

    return (
        `${market}:${symbol}:${signal}`
    );
}

function canSendAlert(
    market,
    symbol,
    signal
) {

    const key =
        alertKey(
            market,
            symbol,
            signal
        );

    const previous =
        alertMemory.get(key) || 0;

    return (
        Date.now() -
        previous >=
        ALERT_COOLDOWN
    );
}

function markAlert(
    market,
    symbol,
    signal
) {

    const key =
        alertKey(
            market,
            symbol,
            signal
        );

    alertMemory.set(
        key,
        Date.now()
    );
}

/* =========================================================
   🤖 TELEGRAM
========================================================= */

const bots = {
    TASI: null,
    US: null,
    CRYPTO: null
};

function addChat(
    market,
    chatId
) {

    if (
        !state[market].includes(
            chatId
        )
    ) {

        state[market].push(
            chatId
        );

        saveState();
    }
}

function removeChat(
    market,
    chatId
) {

    state[market] =
        state[market].filter(
            id => id !== chatId
        );

    saveState();
}

/* =========================================================
   👋 رسالة البداية
========================================================= */

function welcomeMessage(
    market
) {

    const labels = {

        TASI:
            "السوق السعودي 🇸🇦",

        US:
            "السوق الأمريكي 🇺🇸",

        CRYPTO:
            "العملات الرقمية 🪙"
    };

    return (
`💀🚀 <b>AI PRO MAX</b>

✅ البوت يعمل الآن

🔄 الفحص تلقائي وكامل
⏱️ الفحص كل دقيقتين

📊 السوق:
${labels[market]}

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

🤖 لا تحتاج إلى تشغيل الفحص يدويًا.

📡 مصدر البيانات:
EODHD فقط`
    );
}

/* =========================================================
   📢 رسالة الإشارة
========================================================= */

function buildSignalMessage(
    stock
) {

    const marketName = {

        TASI:
            "🇸🇦 TASI",

        US:
            "🇺🇸 US",

        CRYPTO:
            "🪙 CRYPTO"

    }[stock.market];

    const signal =
        stock.signal === "BUY"
            ? "🟢 شراء قوي"
            : "🔴 بيع قوي";

    const companyName =
        universe[
            stock.market
        ]
        .names
        .get(stock.symbol) ||
        stock.symbol;

    let targetsText = "";

    for (
        const target
        of stock.targets
    ) {

        targetsText +=
`🎯 TP${target.number}: <b>${money(target.price)}</b> (${percentage(target.percentage)})
`;
    }

    return (
`💀🚀 <b>AI PRO MAX SIGNAL</b>

${marketName}

<b>${stock.symbol}</b>
${companyName}

${signal}

━━━━━━━━━━━━━━━━

💰 السعر:
<b>${money(stock.price)}</b>

📈 التغير:
<b>${percentage(stock.changeP)}</b>

🧠 القوة:
<b>${stock.score}/100</b>

🟢 BUY POWER:
<b>${stock.buyScore}%</b>

🔴 SELL POWER:
<b>${stock.sellScore}%</b>

━━━━━━━━━━━━━━━━

📊 EMA8:
${money(stock.ema8)}

📊 EMA21:
${money(stock.ema21)}

📊 EMA50:
${money(stock.ema50)}

📟 RSI14:
<b>${stock.rsi14.toFixed(1)}</b>

🔥 ATR14:
<b>${money(stock.atr14)}</b>

📦 قوة الحجم:
<b>${stock.volumeStrength.toFixed(2)}x</b>

━━━━━━━━━━━━━━━━

🟢 الدعم:
<b>${money(stock.support)}</b>

🔴 المقاومة:
<b>${money(stock.resistance)}</b>

📈 الاتجاه:
<b>${stock.trend}</b>

━━━━━━━━━━━━━━━━

<b>🎯 أهداف ATR الثمانية</b>

${targetsText}

━━━━━━━━━━━━━━━━

⏱️ ${new Date().toLocaleString("ar-SA")}`
    );
}

/* =========================================================
   📤 إرسال الرسائل
========================================================= */

async function sendToMarket(
    market,
    message
) {

    const bot =
        bots[market];

    if (!bot) {
        return;
    }

    const subscribers =
        [
            ...state[market]
        ];

    for (
        const chatId
        of subscribers
    ) {

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

            const text =
                String(
                    error.message ||
                    ""
                );

            if (
                /chat not found|bot was blocked|user is deactivated/i.test(
                    text
                )
            ) {

                removeChat(
                    market,
                    chatId
                );

            } else {

                logErrorOnce(
                    `TG_${market}_${chatId}_${text}`,
                    `❌ Telegram ${market}: ${text}`,
                    10 * 60 * 1000
                );
            }
        }
    }
}

/* =========================================================
   🤖 إنشاء بوت
========================================================= */

function createTelegramBot(
    market,
    token
) {

    if (!token) {

        log(
            `⚠️ ${market}: لا يوجد Token`
        );

        return null;
    }

    const bot =
        new TelegramBot(
            token,
            {
                polling: {
                    autoStart: true,
                    params: {
                        timeout: 20
                    }
                }
            }
        );

    /* /start */

    bot.onText(
        /^\/start(?:@\w+)?$/i,
        async message => {

            addChat(
                market,
                message.chat.id
            );

            try {

                await bot.sendMessage(
                    message.chat.id,
                    welcomeMessage(
                        market
                    ),
                    {
                        parse_mode:
                            "HTML",
                        disable_web_page_preview:
                            true
                    }
                );

            } catch (error) {

                logErrorOnce(
                    `START_${market}_${error.message}`,
                    `❌ Telegram START ${market}: ${error.message}`
                );
            }
        }
    );

    /* /status */

    bot.onText(
        /^\/status(?:@\w+)?$/i,
        async message => {

            const u =
                universe[market];

            const text =
`💀🚀 <b>AI PRO MAX STATUS</b>

📊 السوق:
${market}

🟢 الحالة:
يعمل

📦 الرموز:
${u.symbols.length.toLocaleString("en-US")}

👥 المشتركين:
${state[market].length}

🔄 الفحص:
كل دقيقتين

📡 المصدر:
EODHD`;

            try {

                await bot.sendMessage(
                    message.chat.id,
                    text,
                    {
                        parse_mode:
                            "HTML"
                    }
                );

            } catch (_) {}
        }
    );

    /* Telegram polling errors */

    bot.on(
        "polling_error",
        error => {

            const message =
                String(
                    error.message ||
                    error
                );

            if (
                /409 Conflict/i.test(
                    message
                )
            ) {

                logErrorOnce(
                    `TG409_${market}`,
                    `🚨 ${market}: Telegram 409 — يوجد تشغيل آخر لنفس البوت.`,
                    2 * 60 * 1000
                );

            } else {

                logErrorOnce(
                    `POLL_${market}_${message}`,
                    `❌ Telegram polling ${market}: ${message}`,
                    5 * 60 * 1000
                );
            }
        }
    );

    bot.on(
        "error",
        error => {

            logErrorOnce(
                `BOT_${market}_${error.message}`,
                `❌ Telegram bot ${market}: ${error.message}`
            );
        }
    );

    log(
        `🤖 ${market} Telegram بدأ`
    );

    return bot;
}

/* =========================================================
   🔎 فحص السوق
========================================================= */

async function scanMarket(
    market
) {

    const symbols =
        await ensureUniverse(
            market
        );

    if (!symbols.length) {

        logErrorOnce(
            `EMPTY_${market}`,
            `⛔ ${market}: فشل تحميل قائمة الرموز من EODHD. السوق ليس فارغًا.`,
            10 * 60 * 1000
        );

        return;
    }

    log(
        `🔎 ${market}: فحص ${symbols.length.toLocaleString("en-US")} رمز`
    );

    const quotes =
        await getQuotes(
            symbols,
            market
        );

    if (!quotes.length) {

        logErrorOnce(
            `NO_QUOTES_${market}`,
            `⛔ ${market}: قائمة الرموز موجودة لكن لم تصل أسعار من EODHD.`,
            10 * 60 * 1000
        );

        return;
    }

    /* =====================================================
       💵 شرط السعر الأمريكي
    ===================================================== */

    const filtered =
        quotes.filter(
            quote => {

                if (
                    market === "US" &&
                    quote.price < 0.20
                ) {

                    return false;
                }

                return quote.price > 0;
            }
        );

    /* =====================================================
       🧠 ترتيب المرشحين
    ===================================================== */

    filtered.sort(
        (a, b) => {

            const scoreA =
                Math.abs(
                    a.changeP
                ) * 5 +
                Math.log10(
                    Math.max(
                        a.volume,
                        1
                    )
                ) * 2 +
                (
                    a.changeP > 0
                        ? 3
                        : 0
                );

            const scoreB =
                Math.abs(
                    b.changeP
                ) * 5 +
                Math.log10(
                    Math.max(
                        b.volume,
                        1
                    )
                ) * 2 +
                (
                    b.changeP > 0
                        ? 3
                        : 0
                );

            return scoreB - scoreA;
        }
    );

    /* =====================================================
       🔬 التحليل العميق
    ===================================================== */

    const candidateCount =
        market === "US"
            ? 10
            : 8;

    const candidates =
        filtered.slice(
            0,
            candidateCount
        );

    const strongSignals = [];

    for (
        const quote
        of candidates
    ) {

        try {

            const result =
                await analyzeStock(
                    quote
                );

            if (
                result.signal === "BUY" ||
                result.signal === "SELL"
            ) {

                strongSignals.push(
                    result
                );
            }

        } catch (error) {

            logErrorOnce(
                `ANALYZE_${quote.symbol}_${error.message}`,
                `⚠️ تحليل ${quote.symbol}: ${error.message}`,
                30 * 60 * 1000
            );
        }
    }

    strongSignals.sort(
        (a, b) =>
            b.score -
            a.score
    );

    log(
        `✅ ${market}: أسعار=${quotes.length} | مرشحون=${candidates.length} | إشارات=${strongSignals.length}`
    );

    /* =====================================================
       🚨 إرسال أقوى الإشارات
    ===================================================== */

    for (
        const stock
        of strongSignals.slice(0, 5)
    ) {

        if (
            !canSendAlert(
                market,
                stock.symbol,
                stock.signal
            )
        ) {

            continue;
        }

        markAlert(
            market,
            stock.symbol,
            stock.signal
        );

        const message =
            buildSignalMessage(
                stock
            );

        await sendToMarket(
            market,
            message
        );

        /* =================================================
           📰 الخبر اختياري
        ================================================= */

        try {

            const news =
                await getNews(
                    stock.symbol
                );

            if (
                news &&
                news.title
            ) {

                await sendToMarket(
                    market,
`📰 <b>خبر ${stock.symbol}</b>

${news.title}

المصدر:
${news.source || "EODHD"}`
                );
            }

        } catch (_) {}
    }
}

/* =========================================================
   🔄 دورة الفحص الكاملة
========================================================= */

let scanRunning = false;

async function fullScan() {

    if (scanRunning) {

        log(
            "⏳ دورة سابقة ما زالت تعمل — تم تجاوز الدورة الحالية."
        );

        return;
    }

    scanRunning = true;

    try {

        await scanMarket(
            "TASI"
        );

        await scanMarket(
            "US"
        );

        await scanMarket(
            "CRYPTO"
        );

    } catch (error) {

        logErrorOnce(
            `FULLSCAN_${error.message}`,
            `❌ خطأ دورة الفحص: ${error.message}`
        );

    } finally {

        scanRunning = false;
    }
}

/* =========================================================
   🌐 EXPRESS SERVER
========================================================= */

const app =
    express();

app.get(
    "/",
    (_request, response) => {

        response.json({

            ok: true,

            name:
                "AI PRO MAX",

            status:
                "running",

            scan:
                "every 2 minutes",

            source:
                "EODHD",

            markets: {

                TASI:
                    universe
                        .TASI
                        .symbols
                        .length,

                US:
                    universe
                        .US
                        .symbols
                        .length,

                CRYPTO:
                    universe
                        .CRYPTO
                        .symbols
                        .length
            },

            subscribers: {

                TASI:
                    state.TASI.length,

                US:
                    state.US.length,

                CRYPTO:
                    state.CRYPTO.length
            },

            time:
                new Date()
                    .toISOString()
        });
    }
);

app.get(
    "/health",
    (_request, response) => {

        response
            .status(200)
            .send(
                "AI PRO MAX OK"
            );
    }
);

app.listen(
    PORT,
    () => {

        log(
            `🌐 Server يعمل على PORT ${PORT}`
        );
    }
);

/* =========================================================
   🚀 START
========================================================= */

async function start() {

    try {

        checkConfig();

        /* Telegram */

        bots.TASI =
            createTelegramBot(
                "TASI",
                TASI_TOKEN
            );

        bots.US =
            createTelegramBot(
                "US",
                US_TOKEN
            );

        bots.CRYPTO =
            createTelegramBot(
                "CRYPTO",
                CRYPTO_TOKEN
            );

        log(
            "================================================"
        );

        log(
            "💀🚀 AI PRO MAX بدأ التشغيل"
        );

        log(
            "🇸🇦 TASI BOT: ON"
        );

        log(
            "🇺🇸 US BOT: ON"
        );

        log(
            "🪙 CRYPTO BOT: ON"
        );

        log(
            "📡 DATA: EODHD ONLY"
        );

        log(
            "🔄 SCAN: EVERY 2 MINUTES"
        );

        log(
            "================================================"
        );

        await sleep(
            3000
        );

        /* أول فحص */

        await fullScan();

        /* الفحص التلقائي */

        setInterval(
            () => {

                fullScan()
                    .catch(
                        error => {

                            logErrorOnce(
                                `INTERVAL_${error.message}`,
                                `❌ خطأ interval: ${error.message}`
                            );
                        }
                    );

            },
            SCAN_INTERVAL
        );

    } catch (error) {

        console.error(
            "💥 START ERROR:",
            error.message
        );

        process.exitCode = 1;
    }
}

/* =========================================================
   🛡️ حماية العملية
========================================================= */

process.on(
    "unhandledRejection",
    error => {

        logErrorOnce(
            `UNHANDLED_${String(error)}`,
            `❌ unhandledRejection: ${String(error)}`
        );
    }
);

process.on(
    "uncaughtException",
    error => {

        console.error(
            "💥 uncaughtException:",
            error
        );
    }
);

/* =========================================================
   ▶️ تشغيل
========================================================= */

start();