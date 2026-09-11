
"use strict";

/*
============================================================
💀🚀 AI PRO MAX
AUTONOMOUS TASI + US + CRYPTO TELEGRAM SCANNER
============================================================

مصدر البيانات:
EODHD API فقط

متغيرات Railway:
TASI_CONFIG
US_CONFIG
CRYPTO_CONFIG
EODHD_API_KEY

الفحص:
كل دقيقتين

التحليل:
EMA 8 / 21 / 50
RSI 14
ATR 14
Support / Resistance
Volume Strength
Buy Power
Sell Power
8 ATR Targets
منع تكرار التنبيهات

لا يوجد:
Yahoo
Twelve Data
TradingView
أي مصدر أسعار خارجي
============================================================
*/

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const fs = require("fs");
const path = require("path");

/* =========================================================
   CONFIG
========================================================= */

const PORT = Number(process.env.PORT || 3000);

const TASI_TOKEN =
    String(process.env.TASI_CONFIG || "").trim();

const US_TOKEN =
    String(process.env.US_CONFIG || "").trim();

const CRYPTO_TOKEN =
    String(process.env.CRYPTO_CONFIG || "").trim();

const EODHD_KEY =
    String(process.env.EODHD_API_KEY || "").trim();

const SCAN_INTERVAL =
    2 * 60 * 1000;

const UNIVERSE_CACHE =
    6 * 60 * 60 * 1000;

const ANALYSIS_CACHE =
    10 * 60 * 1000;

const ALERT_COOLDOWN =
    30 * 60 * 1000;

const STATE_FILE =
    path.join(__dirname, "chat_ids.json");

/* =========================================================
   LOG
========================================================= */

function log(message) {
    console.log(
        `${new Date().toISOString()} | ${message}`
    );
}

const errorCache = new Map();

function logErrorOnce(
    key,
    message,
    cooldown = 10 * 60 * 1000
) {
    const now = Date.now();

    const last =
        errorCache.get(key) || 0;

    if (
        now - last >= cooldown
    ) {
        errorCache.set(key, now);
        log(message);
    }
}

/* =========================================================
   STATE
========================================================= */

let state = {
    TASI: [],
    US: [],
    CRYPTO: []
};

try {
    if (fs.existsSync(STATE_FILE)) {
        const loaded =
            JSON.parse(
                fs.readFileSync(
                    STATE_FILE,
                    "utf8"
                )
            );

        if (
            loaded &&
            typeof loaded === "object"
        ) {
            state = loaded;
        }
    }
} catch (error) {
    log(
        `⚠️ قراءة chat_ids.json: ${error.message}`
    );
}

for (
    const market of
    ["TASI", "US", "CRYPTO"]
) {
    if (
        !Array.isArray(
            state[market]
        )
    ) {
        state[market] = [];
    }
}

function saveState() {
    try {
        fs.writeFileSync(
            STATE_FILE,
            JSON.stringify(
                state,
                null,
                2
            ),
            "utf8"
        );
    } catch (error) {
        log(
            `⚠️ حفظ الحالة: ${error.message}`
        );
    }
}

/* =========================================================
   CONFIG CHECK
========================================================= */

function checkConfig() {

    log("================================================");
    log("💀🚀 تشغيل AI PRO MAX");
    log("================================================");

    if (!TASI_TOKEN) {
        throw new Error(
            "TASI_CONFIG غير موجود"
        );
    }

    if (!US_TOKEN) {
        throw new Error(
            "US_CONFIG غير موجود"
        );
    }

    if (!CRYPTO_TOKEN) {
        throw new Error(
            "CRYPTO_CONFIG غير موجود"
        );
    }

    if (!EODHD_KEY) {
        throw new Error(
            "EODHD_API_KEY غير موجود"
        );
    }

    log("✅ TASI_CONFIG موجود");
    log("✅ US_CONFIG موجود");
    log("✅ CRYPTO_CONFIG موجود");
    log("✅ EODHD_API_KEY موجود");

    log("📡 مصدر البيانات: EODHD فقط");
    log("🔄 الفحص: كل دقيقتين");
}

/* =========================================================
   EODHD
========================================================= */

function eodhdURL(
    endpoint,
    params = {}
) {

    const url =
        new URL(
            "https://eodhd.com/api/" +
            endpoint.replace(/^\/+/, "")
        );

    url.searchParams.set(
        "api_token",
        EODHD_KEY
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

    return url.toString();
}

async function eodhd(
    endpoint,
    params = {},
    timeout = 30000
) {

    const controller =
        new AbortController();

    const timer =
        setTimeout(
            () =>
                controller.abort(),
            timeout
        );

    try {

        const response =
            await fetch(
                eodhdURL(
                    endpoint,
                    params
                ),
                {
                    method: "GET",
                    headers: {
                        Accept:
                            "application/json",
                        "User-Agent":
                            "AI-PRO-MAX"
                    },
                    signal:
                        controller.signal
                }
            );

        const text =
            await response.text();

        let data;

        try {
            data =
                JSON.parse(text);
        } catch {
            data = text;
        }

        if (!response.ok) {

            let message = "";

            if (
                data &&
                typeof data === "object"
            ) {

                message =
                    data.message ||
                    data.error ||
                    data.detail ||
                    "";
            }

            if (!message) {
                message =
                    String(data)
                        .slice(0, 500);
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

    } catch (error) {

        if (
            error.name ===
            "AbortError"
        ) {

            throw new Error(
                "EODHD TIMEOUT"
            );
        }

        throw error;

    } finally {

        clearTimeout(timer);
    }
}

/* =========================================================
   HELPERS
========================================================= */

function n(
    value,
    fallback = 0
) {

    const number =
        Number(value);

    return Number.isFinite(number)
        ? number
        : fallback;
}

function unique(array) {
    return [
        ...new Set(array)
    ];
}

function chunks(
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

function sleep(ms) {
    return new Promise(
        resolve =>
            setTimeout(
                resolve,
                ms
            )
    );
}

function money(value) {

    const number =
        n(value);

    if (!number) {
        return "—";
    }

    if (
        Math.abs(number) >= 1000
    ) {

        return number.toLocaleString(
            "en-US",
            {
                maximumFractionDigits: 2
            }
        );
    }

    return number
        .toFixed(6)
        .replace(/0+$/, "")
        .replace(/\.$/, "");
}

function percent(value) {

    const number =
        n(value);

    return (
        `${number >= 0 ? "+" : ""}${number.toFixed(2)}%`
    );
}

function compact(value) {

    const number =
        n(value);

    const abs =
        Math.abs(number);

    if (abs >= 1e9) {
        return (
            (number / 1e9)
                .toFixed(2) +
            "B"
        );
    }

    if (abs >= 1e6) {
        return (
            (number / 1e6)
                .toFixed(2) +
            "M"
        );
    }

    if (abs >= 1e3) {
        return (
            (number / 1e3)
                .toFixed(2) +
            "K"
        );
    }

    return Math.round(number)
        .toLocaleString("en-US");
}

/* =========================================================
   EMA
========================================================= */

function EMA(
    values,
    length
) {

    if (!values.length) {
        return [];
    }

    const result =
        new Array(
            values.length
        );

    const multiplier =
        2 / (length + 1);

    result[0] =
        values[0];

    for (
        let i = 1;
        i < values.length;
        i++
    ) {

        result[i] =
            (
                values[i] *
                multiplier
            ) +
            (
                result[i - 1] *
                (1 - multiplier)
            );
    }

    return result;
}

/* =========================================================
   RSI
========================================================= */

function RSI(
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

        if (
            difference > 0
        ) {
            gain += difference;
        } else {
            loss +=
                Math.abs(
                    difference
                );
        }
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
                gain *
                (length - 1) +
                currentGain
            ) / length;

        loss =
            (
                loss *
                (length - 1) +
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
   ATR
========================================================= */

function ATR(
    candles,
    length = 14
) {

    if (
        candles.length <
        length + 1
    ) {

        return 0;
    }

    const ranges = [];

    for (
        let i = 1;
        i < candles.length;
        i++
    ) {

        const high =
            n(candles[i].high);

        const low =
            n(candles[i].low);

        const previousClose =
            n(
                candles[i - 1].close
            );

        ranges.push(
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
            )
        );
    }

    if (
        ranges.length < length
    ) {
        return 0;
    }

    let atr =
        ranges
            .slice(0, length)
            .reduce(
                (a, b) => a + b,
                0
            ) / length;

    for (
        let i = length;
        i < ranges.length;
        i++
    ) {

        atr =
            (
                atr *
                (length - 1) +
                ranges[i]
            ) / length;
    }

    return atr;
}

/* =========================================================
   UNIVERSE
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
   🇸🇦 DISCOVER SAUDI EXCHANGE
========================================================= */

let cachedSaudiExchange = null;

async function findSaudiExchange() {

    if (cachedSaudiExchange) {
        return cachedSaudiExchange;
    }

    const exchanges =
        await eodhd(
            "exchanges-list/",
            {},
            30000
        );

    if (
        !Array.isArray(exchanges)
    ) {

        throw new Error(
            "EODHD لم يرجع قائمة البورصات"
        );
    }

    const candidates =
        exchanges.filter(
            exchange => {

                const text =
                    [
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
                    text.includes(
                        "saudi"
                    ) ||
                    text.includes(
                        "tadawul"
                    ) ||
                    String(
                        exchange.CountryISO2 ||
                        ""
                    ).toUpperCase() ===
                    "SA" ||
                    String(
                        exchange.CountryISO3 ||
                        ""
                    ).toUpperCase() ===
                    "SAU"
                );
            }
        );

    if (
        !candidates.length
    ) {

        throw new Error(
            "لم يتم العثور على بورصة السعودية داخل EODHD"
        );
    }

    const preferred =
        candidates.find(
            x =>
                /tadawul/i.test(
                    String(
                        x.Name || ""
                    )
                )
        ) ||
        candidates.find(
            x =>
                String(
                    x.Currency || ""
                ).toUpperCase() ===
                "SAR"
        ) ||
        candidates[0];

    cachedSaudiExchange =
        String(
            preferred.Code || ""
        ).trim();

    if (
        !cachedSaudiExchange
    ) {

        throw new Error(
            "رمز بورصة السعودية غير موجود في رد EODHD"
        );
    }

    log(
        `🇸🇦 بورصة السعودية: ${cachedSaudiExchange}`
    );

    return cachedSaudiExchange;
}

/* =========================================================
   SYMBOL LIST
========================================================= */

async function getSymbols(
    exchange
) {

    return await eodhd(
        `exchange-symbol-list/${encodeURIComponent(exchange)}`,
        {},
        60000
    );
}

/* =========================================================
   TASI
========================================================= */

async function loadTASI() {

    const exchange =
        await findSaudiExchange();

    const rows =
        await getSymbols(
            exchange
        );

    if (
        !Array.isArray(rows)
    ) {

        throw new Error(
            "قائمة TASI غير صالحة"
        );
    }

    const symbols = [];
    const names =
        new Map();

    for (
        const row of rows
    ) {

        const code =
            String(
                row.Code ||
                row.code ||
                ""
            ).trim();

        if (!code) {
            continue;
        }

        const type =
            String(
                row.Type ||
                row.type ||
                ""
            ).toLowerCase();

        if (
            type &&
            !(
                type.includes(
                    "common"
                ) ||
                type.includes(
                    "stock"
                )
            )
        ) {
            continue;
        }

        const symbol =
            code.includes(".")
                ? code
                : `${code}.${exchange}`;

        const name =
            String(
                row.Name ||
                row.name ||
                code
            );

        symbols.push(
            symbol
        );

        names.set(
            symbol,
            name
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
        `🇸🇦 TASI: تم تحميل ${universe.TASI.symbols.length} رمز`
    );
}

/* =========================================================
   US
========================================================= */

async function loadUS() {

    const rows =
        await getSymbols(
            "US"
        );

    if (
        !Array.isArray(rows)
    ) {

        throw new Error(
            "قائمة US غير صالحة"
        );
    }

    const symbols = [];
    const names =
        new Map();

    for (
        const row of rows
    ) {

        const code =
            String(
                row.Code ||
                row.code ||
                ""
            ).trim();

        if (!code) {
            continue;
        }

        const type =
            String(
                row.Type ||
                row.type ||
                ""
            ).toLowerCase();

        const name =
            String(
                row.Name ||
                row.name ||
                code
            );

        const exchange =
            String(
                row.Exchange ||
                row.exchange ||
                ""
            ).toUpperCase();

        if (
            /OTC|PINK|GREY|NMFQS/.test(
                exchange
            )
        ) {
            continue;
        }

        if (
            type &&
            !(
                type.includes(
                    "common"
                ) ||
                type.includes(
                    "stock"
                )
            )
        ) {
            continue;
        }

        const symbol =
            code.toUpperCase()
                .includes(".")
                ? code.toUpperCase()
                : `${code.toUpperCase()}.US`;

        symbols.push(
            symbol
        );

        names.set(
            symbol,
            name
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
        `🇺🇸 US: تم تحميل ${universe.US.symbols.length} رمز`
    );
}

/* =========================================================
   CRYPTO
========================================================= */

async function loadCRYPTO() {

    const rows =
        await getSymbols(
            "CC"
        );

    if (
        !Array.isArray(rows)
    ) {

        throw new Error(
            "قائمة CRYPTO غير صالحة"
        );
    }

    const symbols = [];
    const names =
        new Map();

    for (
        const row of rows
    ) {

        const code =
            String(
                row.Code ||
                row.code ||
                ""
            ).trim();

        if (!code) {
            continue;
        }

        const symbol =
            code.includes(".")
                ? code.toUpperCase()
                : `${code.toUpperCase()}.CC`;

        const name =
            String(
                row.Name ||
                row.name ||
                code
            );

        symbols.push(
            symbol
        );

        names.set(
            symbol,
            name
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
        `🪙 CRYPTO: تم تحميل ${universe.CRYPTO.symbols.length} رمز`
    );
}

/* =========================================================
   LOAD ALL
========================================================= */

async function loadAllUniverses() {

    const jobs = [
        [
            "TASI",
            loadTASI
        ],
        [
            "US",
            loadUS
        ],
        [
            "CRYPTO",
            loadCRYPTO
        ]
    ];

    for (
        const [
            market,
            loader
        ]
        of jobs
    ) {

        const current =
            universe[market];

        if (
            current.symbols.length &&
            Date.now() -
            current.loadedAt <
            UNIVERSE_CACHE
        ) {
            continue;
        }

        try {

            await loader();

        } catch (error) {

            logErrorOnce(
                `UNIVERSE_${market}_${error.message}`,
                `❌ ${market}: فشل تحميل الرموز — ${error.message}`,
                15 * 60 * 1000
            );
        }

        await sleep(500);
    }
}

/* =========================================================
   QUOTE
========================================================= */

function normalizeQuote(
    item,
    market
) {

    if (
        !item ||
        typeof item !== "object"
    ) {
        return null;
    }

    const symbol =
        String(
            item.code ||
            item.Code ||
            item.symbol ||
            item.Symbol ||
            item.s ||
            ""
        ).trim();

    const price =
        n(
            item.close ??
            item.price ??
            item.last
        );

    if (
        !symbol ||
        price <= 0
    ) {
        return null;
    }

    const previousClose =
        n(
            item.previousClose ??
            item.prevClose
        );

    let change =
        n(
            item.change_p ??
            item.changePercent
        );

    if (
        !change &&
        previousClose
    ) {

        change =
            (
                (
                    price -
                    previousClose
                ) /
                previousClose
            ) * 100;
    }

    return {
        symbol,
        price,
        open:
            n(item.open),
        high:
            n(item.high),
        low:
            n(item.low),
        volume:
            n(item.volume),
        previousClose,
        change,
        market
    };
}

/* =========================================================
   GET QUOTES BATCH
========================================================= */

async function getQuotes(
    symbols,
    market
) {

    if (!symbols.length) {
        return [];
    }

    const results = [];

    /*
      عدد الرموز في الطلب الواحد
    */

    const batchSize =
        100;

    const batches =
        chunks(
            symbols,
            batchSize
        );

    for (
        const batch
        of batches
    ) {

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
                            rest ||
                            undefined
                    },
                    30000
                );

            if (
                Array.isArray(data)
            ) {

                for (
                    const item
                    of data
                ) {

                    const quote =
                        normalizeQuote(
                            item,
                            market
                        );

                    if (quote) {
                        results.push(
                            quote
                        );
                    }
                }

            } else {

                const quote =
                    normalizeQuote(
                        data,
                        market
                    );

                if (quote) {
                    results.push(
                        quote
                    );
                }
            }

            await sleep(100);

        } catch (error) {

            logErrorOnce(
                `QUOTE_${market}_${error.message}`,
                `❌ ${market}: فشل جلب الأسعار — ${error.message}`,
                15 * 60 * 1000
            );

            /*
              إذا كان الخطأ 402/403
              لا نكرر آلاف الطلبات
            */

            if (
                /HTTP 402|HTTP 403|HTTP 401/.test(
                    error.message
                )
            ) {

                break;
            }
        }
    }

    const seen =
        new Set();

    return results.filter(
        item => {

            const key =
                `${market}:${item.symbol}`;

            if (
                seen.has(key)
            ) {
                return false;
            }

            seen.add(key);

            return true;
        }
    );
}

/* =========================================================
   DAILY DATA
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
            180 * 86400000
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
   INTRADAY
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
        3 * 86400;

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
   ANALYSIS CACHE
========================================================= */

const analysisCache =
    new Map();

function getCachedAnalysis(
    symbol
) {

    const cached =
        analysisCache.get(
            symbol
        );

    if (!cached) {
        return null;
    }

    if (
        Date.now() -
        cached.time >
        ANALYSIS_CACHE
    ) {

        analysisCache.delete(
            symbol
        );

        return null;
    }

    return cached.data;
}

/* =========================================================
   SUPPORT / RESISTANCE
========================================================= */

function supportResistance(
    candles
) {

    if (
        !Array.isArray(candles) ||
        candles.length < 10
    ) {

        return {
            support: 0,
            resistance: 0
        };
    }

    const recent =
        candles.slice(-50);

    const lows =
        recent
            .map(
                x => n(x.low)
            )
            .filter(
                x => x > 0
            );

    const highs =
        recent
            .map(
                x => n(x.high)
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
   VOLUME
========================================================= */

function volumePower(
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
                x => n(x.volume)
            )
            .filter(
                x => x > 0
            );

    if (
        volumes.length < 10
    ) {
        return 1;
    }

    const recent =
        volumes.slice(-5);

    const base =
        volumes.slice(-20);

    const recentAverage =
        recent.reduce(
            (a, b) => a + b,
            0
        ) / recent.length;

    const baseAverage =
        base.reduce(
            (a, b) => a + b,
            0
        ) / base.length;

    if (!baseAverage) {
        return 1;
    }

    return (
        recentAverage /
        baseAverage
    );
}

/* =========================================================
   ATR TARGETS
========================================================= */

function atrTargets(
    price,
    atr,
    direction
) {

    const safeATR =
        Math.max(
            atr,
            price * 0.005
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
   DEEP ANALYSIS
========================================================= */

async function analyze(
    quote
) {

    const cached =
        getCachedAnalysis(
            quote.symbol
        );

    if (cached) {

        return {
            ...quote,
            ...cached
        };
    }

    let daily = [];
    let intraday = [];

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
            `⚠️ ${quote.symbol}: Daily — ${error.message}`,
            30 * 60 * 1000
        );
    }

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
            `⚠️ ${quote.symbol}: Intraday — ${error.message}`,
            30 * 60 * 1000
        );
    }

    const candles =
        intraday.length >= 30
            ? intraday
            : daily;

    const closes =
        candles
            .map(
                x => n(x.close)
            )
            .filter(
                x => x > 0
            );

    let ema8 =
        quote.price;

    let ema21 =
        quote.price;

    let ema50 =
        quote.price;

    if (
        closes.length >= 8
    ) {

        ema8 =
            EMA(
                closes,
                8
            ).at(-1);
    }

    if (
        closes.length >= 21
    ) {

        ema21 =
            EMA(
                closes,
                21
            ).at(-1);
    }

    if (
        closes.length >= 50
    ) {

        ema50 =
            EMA(
                closes,
                50
            ).at(-1);
    }

    const rsi14 =
        closes.length >= 15
            ? RSI(
                closes,
                14
            )
            : 50;

    const atr14 =
        candles.length >= 15
            ? ATR(
                candles,
                14
            )
            : quote.price *
              0.01;

    const sr =
        supportResistance(
            daily.length
                ? daily
                : candles
        );

    const volume =
        volumePower(
            candles
        );

    /* =====================================================
       BUY SCORE
    ===================================================== */

    let buy = 0;
    let sell = 0;

    /* EMA TREND */

    if (
        ema8 > ema21
    ) {
        buy += 20;
    }

    if (
        ema21 > ema50
    ) {
        buy += 20;
    }

    if (
        ema8 < ema21
    ) {
        sell += 20;
    }

    if (
        ema21 < ema50
    ) {
        sell += 20;
    }

    /* PRICE */

    if (
        quote.change > 0
    ) {

        buy += Math.min(
            15,
            quote.change * 2
        );
    }

    if (
        quote.change < 0
    ) {

        sell += Math.min(
            15,
            Math.abs(
                quote.change
            ) * 2
        );
    }

    /* RSI */

    if (
        rsi14 >= 55 &&
        rsi14 <= 80
    ) {

        buy += 15;
    }

    if (
        rsi14 <= 45 &&
        rsi14 >= 20
    ) {

        sell += 15;
    }

    /* VOLUME */

    if (
        volume >= 1.5
    ) {

        if (
            quote.change >= 0
        ) {

            buy += 15;

        } else {

            sell += 15;
        }
    }

    /* SUPPORT */

    if (
        sr.support > 0 &&
        quote.price >=
        sr.support
    ) {

        buy += 10;
    }

    /* RESISTANCE */

    if (
        sr.resistance > 0 &&
        quote.price <=
        sr.resistance
    ) {

        sell += 10;
    }

    buy =
        Math.max(
            0,
            Math.min(
                100,
                Math.round(buy)
            )
        );

    sell =
        Math.max(
            0,
            Math.min(
                100,
                Math.round(sell)
            )
        );

    let signal =
        "WATCH";

    let score =
        Math.max(
            buy,
            sell
        );

    if (
        buy >= 75 &&
        buy >= sell + 10
    ) {

        signal =
            "BUY";
    }

    if (
        sell >= 75 &&
        sell >= buy + 10
    ) {

        signal =
            "SELL";
    }

    const direction =
        signal === "SELL"
            ? "SELL"
            : "BUY";

    const targets =
        atrTargets(
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

        volumeStrength:
            volume,

        buyPower:
            buy,

        sellPower:
            sell,

        score,

        signal,

        trend:
            ema8 > ema21 &&
            ema21 > ema50
                ? "صاعد قوي"
                :
            ema8 < ema21 &&
            ema21 < ema50
                ? "هابط قوي"
                :
                "متذبذب",

        targets
    };

    analysisCache.set(
        quote.symbol,
        {
            time:
                Date.now(),
            data:
                result
        }
    );

    return {
        ...quote,
        ...result
    };
}

/* =========================================================
   ALERT MEMORY
========================================================= */

const alertMemory =
    new Map();

function canAlert(
    market,
    symbol,
    signal
) {

    const key =
        `${market}:${symbol}:${signal}`;

    const last =
        alertMemory.get(
            key
        ) || 0;

    return (
        Date.now() -
        last >=
        ALERT_COOLDOWN
    );
}

function markAlert(
    market,
    symbol,
    signal
) {

    alertMemory.set(
        `${market}:${symbol}:${signal}`,
        Date.now()
    );
}

/* =========================================================
   TELEGRAM
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

/* =========================================================
   WELCOME
========================================================= */

function welcome(
    market
) {

    const names = {

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
<b>${names[market]}</b>

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
<b>EODHD فقط</b>`
    );
}

/* =========================================================
   SIGNAL MESSAGE
========================================================= */

function signalMessage(
    stock
) {

    const marketName = {

        TASI:
            "🇸🇦 السوق السعودي",

        US:
            "🇺🇸 السوق الأمريكي",

        CRYPTO:
            "🪙 العملات الرقمية"

    }[stock.market];

    const signal =
        stock.signal === "BUY"
            ? "🟢 شراء قوي"
            : "🔴 بيع قوي";

    const company =
        universe[
            stock.market
        ]
        .names
        .get(
            stock.symbol
        ) ||
        stock.symbol;

    let targets = "";

    for (
        const target
        of stock.targets
    ) {

        targets +=
`🎯 TP${target.number}: <b>${money(target.price)}</b> (${percent(target.percentage)})
`;
    }

    return (
`💀🚀 <b>AI PRO MAX SIGNAL</b>

${marketName}

<b>${stock.symbol}</b>
${company}

${signal}

━━━━━━━━━━━━━━━━

💰 السعر:
<b>${money(stock.price)}</b>

📈 التغير:
<b>${percent(stock.change)}</b>

🧠 قوة الإشارة:
<b>${stock.score}/100</b>

🟢 قوة الشراء:
<b>${stock.buyPower}%</b>

🔴 قوة البيع:
<b>${stock.sellPower}%</b>

━━━━━━━━━━━━━━━━

📊 EMA 8:
<b>${money(stock.ema8)}</b>

📊 EMA 21:
<b>${money(stock.ema21)}</b>

📊 EMA 50:
<b>${money(stock.ema50)}</b>

📟 RSI 14:
<b>${stock.rsi14.toFixed(1)}</b>

🔥 ATR 14:
<b>${money(stock.atr14)}</b>

📦 قوة الحجم:
<b>${stock.volumeStrength.toFixed(2)}x</b>

📈 الاتجاه:
<b>${stock.trend}</b>

━━━━━━━━━━━━━━━━

🟢 الدعم:
<b>${money(stock.support)}</b>

🔴 المقاومة:
<b>${money(stock.resistance)}</b>

━━━━━━━━━━━━━━━━

🎯 <b>أهداف ATR الثمانية</b>

${targets}

━━━━━━━━━━━━━━━━

⏱️ ${new Date().toLocaleString(
        "ar-SA"
    )}`
    );
}

/* =========================================================
   SEND
========================================================= */

async function sendMarket(
    market,
    message
) {

    const bot =
        bots[market];

    if (!bot) {
        return;
    }

    const chats =
        [
            ...state[market]
        ];

    for (
        const chatId
        of chats
    ) {

        try {

            await bot.sendMessage(
                chatId,
                message,
                {
                    parse_mode:
                        "HTML",
                    disable_web_page_preview:
                        true
                }
            );

        } catch (error) {

            const text =
                String(
                    error.message ||
                    ""
                );

            logErrorOnce(
                `SEND_${market}_${chatId}_${text}`,
                `❌ Telegram ${market}: ${text}`,
                10 * 60 * 1000
            );
        }
    }
}

/* =========================================================
   CREATE BOT
========================================================= */

function createBot(
    market,
    token
) {

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
                    welcome(market),
                    {
                        parse_mode:
                            "HTML"
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

    bot.onText(
        /^\/status(?:@\w+)?$/i,
        async message => {

            const data =
                universe[market];

            const text =
`💀🚀 <b>AI PRO MAX</b>

📊 السوق: ${market}

🟢 الحالة: يعمل

📦 الرموز:
${data.symbols.length.toLocaleString("en-US")}

👥 المشتركين:
${state[market].length}

🔄 الفحص:
كل دقيقتين

📡 البيانات:
EODHD فقط`;

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

    bot.on(
        "polling_error",
        error => {

            const text =
                String(
                    error.message ||
                    error
                );

            if (
                /409 Conflict/i.test(
                    text
                )
            ) {

                logErrorOnce(
                    `409_${market}`,
                    `🚨 ${market}: Telegram 409 — نفس البوت يعمل من نسخة أخرى.`,
                    5 * 60 * 1000
                );

            } else {

                logErrorOnce(
                    `POLL_${market}_${text}`,
                    `❌ Telegram ${market}: ${text}`,
                    10 * 60 * 1000
                );
            }
        }
    );

    bot.on(
        "error",
        error => {

            logErrorOnce(
                `BOT_${market}_${error.message}`,
                `❌ Telegram Bot ${market}: ${error.message}`
            );
        }
    );

    log(
        `🤖 ${market} Telegram: ON`
    );

    return bot;
}

/* =========================================================
   SCAN MARKET
========================================================= */

async function scanMarket(
    market
) {

    const data =
        universe[market];

    if (
        !data.symbols.length
    ) {

        logErrorOnce(
            `EMPTY_${market}`,
            `⛔ ${market}: لا توجد قائمة رموز محملة بسبب فشل EODHD، وليس لأن السوق فارغ.`,
            15 * 60 * 1000
        );

        return;
    }

    log(
        `🔎 ${market}: بدء فحص ${data.symbols.length.toLocaleString("en-US")} رمز`
    );

    const quotes =
        await getQuotes(
            data.symbols,
            market
        );

    if (!quotes.length) {

        logErrorOnce(
            `NOQUOTE_${market}`,
            `⛔ ${market}: EODHD لم يعطِ أسعارًا في هذه الدورة.`,
            15 * 60 * 1000
        );

        return;
    }

    /*
      🇺🇸 السعر الأدنى 0.20$
    */

    const filtered =
        quotes.filter(
            quote => {

                if (
                    market === "US" &&
                    quote.price < 0.20
                ) {
                    return false;
                }

                return true;
            }
        );

    /*
      ترتيب المرشحين
    */

    filtered.sort(
        (a, b) => {

            const scoreA =
                Math.abs(
                    a.change
                ) * 5 +
                Math.log10(
                    Math.max(
                        a.volume,
                        1
                    )
                );

            const scoreB =
                Math.abs(
                    b.change
                ) * 5 +
                Math.log10(
                    Math.max(
                        b.volume,
                        1
                    )
                );

            return (
                scoreB -
                scoreA
            );
        }
    );

    /*
      التحليل العميق
      فقط أقوى المرشحين حتى لا يتم
      استنزاف API بلا داعٍ
    */

    const deepCount =
        market === "US"
            ? 12
            : 10;

    const candidates =
        filtered.slice(
            0,
            deepCount
        );

    const signals = [];

    for (
        const quote
        of candidates
    ) {

        try {

            const result =
                await analyze(
                    quote
                );

            if (
                result.signal ===
                    "BUY" ||
                result.signal ===
                    "SELL"
            ) {

                signals.push(
                    result
                );
            }

        } catch (error) {

            logErrorOnce(
                `ANALYZE_${quote.symbol}_${error.message}`,
                `⚠️ ${quote.symbol}: ${error.message}`,
                30 * 60 * 1000
            );
        }
    }

    signals.sort(
        (a, b) =>
            b.score -
            a.score
    );

    log(
        `✅ ${market}: أسعار=${quotes.length} | تحليل=${candidates.length} | إشارات=${signals.length}`
    );

    /*
      إرسال أقوى 5
    */

    for (
        const signal
        of signals.slice(0, 5)
    ) {

        if (
            !canAlert(
                market,
                signal.symbol,
                signal.signal
            )
        ) {
            continue;
        }

        markAlert(
            market,
            signal.symbol,
            signal.signal
        );

        await sendMarket(
            market,
            signalMessage(
                signal
            )
        );
    }
}

/* =========================================================
   FULL SCAN
========================================================= */

let scanning =
    false;

async function fullScan() {

    if (scanning) {

        log(
            "⏳ توجد دورة فحص سابقة — تم تجاوز الدورة الجديدة"
        );

        return;
    }

    scanning = true;

    try {

        await loadAllUniverses();

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
            `FULL_${error.message}`,
            `❌ دورة الفحص: ${error.message}`
        );

    } finally {

        scanning = false;
    }
}

/* =========================================================
   EXPRESS
========================================================= */

const app =
    express();

app.get(
    "/",
    (_req, res) => {

        res.json({

            ok: true,

            name:
                "AI PRO MAX",

            status:
                "running",

            source:
                "EODHD",

            interval:
                "2 minutes",

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
    (_req, res) => {

        res
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
            `🌐 PORT ${PORT}: يعمل`
        );
    }
);

/* =========================================================
   START
========================================================= */

async function start() {

    try {

        checkConfig();

        bots.TASI =
            createBot(
                "TASI",
                TASI_TOKEN
            );

        bots.US =
            createBot(
                "US",
                US_TOKEN
            );

        bots.CRYPTO =
            createBot(
                "CRYPTO",
                CRYPTO_TOKEN
            );

        log(
            "💀🚀 AI PRO MAX: التشغيل الكامل"
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
            "📡 EODHD: ONLY"
        );

        log(
            "🔄 AUTO SCAN: 2 MIN"
        );

        await sleep(3000);

        /*
          أول فحص
        */

        await fullScan();

        /*
          الفحص المستمر
        */

        setInterval(
            () => {

                fullScan()
                    .catch(
                        error => {

                            logErrorOnce(
                                `INTERVAL_${error.message}`,
                                `❌ Interval: ${error.message}`
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
   PROTECTION
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
   GO
========================================================= */

start();