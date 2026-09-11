
"use strict";

/*
============================================================
💀🚀 AI PRO MAX
AUTONOMOUS TASI + US + CRYPTO TELEGRAM SCANNER
============================================================

مصدر البيانات الوحيد:
EODHD API

لا يوجد:
❌ Yahoo
❌ Twelve Data
❌ TradingView
❌ أي مصدر أسعار خارجي

المتغيرات المطلوبة في Railway:

TASI_CONFIG
US_CONFIG
CRYPTO_CONFIG
EODHD_API_KEY

Node.js 18+
============================================================
*/

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const fs = require("fs");
const path = require("path");

/* =========================================================
   إعدادات أساسية
========================================================= */

const PORT = Number(process.env.PORT || 3000);

const SCAN_INTERVAL = 2 * 60 * 1000;

const EODHD_BASE = "https://eodhd.com/api/";

const MIN_US_PRICE = 0.20;

const EMA_FAST = 8;
const EMA_MID = 21;
const EMA_SLOW = 50;

const RSI_PERIOD = 14;
const ATR_PERIOD = 14;

const TARGETS = 8;

const MAX_DEEP_ANALYSIS = 20;

const MIN_SIGNAL_SCORE = 72;

const ALERT_COOLDOWN = 6 * 60 * 60 * 1000;

const REQUEST_DELAY = 120;

/* =========================================================
   متغيرات Railway
========================================================= */

const TASI_TOKEN = String(process.env.TASI_CONFIG || "").trim();

const US_TOKEN = String(process.env.US_CONFIG || "").trim();

const CRYPTO_TOKEN = String(process.env.CRYPTO_CONFIG || "").trim();

const EODHD_API_KEY = String(process.env.EODHD_API_KEY || "").trim();

/* =========================================================
   Express
========================================================= */

const app = express();

app.get("/", (req, res) => {
    res.status(200).send("AI PRO MAX is running");
});

app.get("/health", (req, res) => {
    res.status(200).json({
        status: "online",
        bot: "AI PRO MAX",
        source: "EODHD",
        interval: "2 minutes"
    });
});

app.listen(PORT, () => {
    console.log(`AI PRO MAX PORT ${PORT}`);
});

/* =========================================================
   التحقق من الإعدادات
========================================================= */

console.log("");
console.log("==============================================");
console.log("💀🚀 AI PRO MAX");
console.log("==============================================");

console.log(
    EODHD_API_KEY
        ? "EODHD_API_KEY: موجود"
        : "EODHD_API_KEY: غير موجود"
);

console.log(
    TASI_TOKEN
        ? "TASI_CONFIG: موجود"
        : "TASI_CONFIG: غير موجود"
);

console.log(
    US_TOKEN
        ? "US_CONFIG: موجود"
        : "US_CONFIG: غير موجود"
);

console.log(
    CRYPTO_TOKEN
        ? "CRYPTO_CONFIG: موجود"
        : "CRYPTO_CONFIG: غير موجود"
);

if (!EODHD_API_KEY) {
    console.log("لا يمكن تشغيل محرك البيانات بدون EODHD_API_KEY");
}

/* =========================================================
   إنشاء البوتات
========================================================= */

let tasiBot = null;
let usBot = null;
let cryptoBot = null;

function createBot(token, market) {

    if (!token) {
        console.log(`${market}: لا يوجد Token`);
        return null;
    }

    const bot = new TelegramBot(token, {
        polling: {
            autoStart: true,
            params: {
                timeout: 30
            }
        }
    });

    bot.on("polling_error", (error) => {

        const text = String(error && error.message || error);

        if (text.includes("409")) {

            console.log(
                `${market}: تم إيقاف polling بسبب تشغيل نسخة أخرى لنفس البوت`
            );

            try {
                bot.stopPolling();
            } catch (_) {}
        } else {

            console.log(
                `${market}: Telegram polling error`
            );
        }
    });

    bot.on("error", () => {
        console.log(`${market}: Telegram error`);
    });

    bot.on("message", async (msg) => {

        if (!msg || !msg.chat || !msg.text) return;

        if (msg.text.trim() === "/start") {

            saveChatId(
                market,
                msg.chat.id
            );

            await sendWelcome(
                bot,
                market,
                msg.chat.id
            );
        }
    });

    console.log(`${market}: Telegram ON`);

    return bot;
}

/* =========================================================
   إنشاء البوتات
========================================================= */

tasiBot = createBot(
    TASI_TOKEN,
    "TASI"
);

usBot = createBot(
    US_TOKEN,
    "US"
);

cryptoBot = createBot(
    CRYPTO_TOKEN,
    "CRYPTO"
);

/* =========================================================
   Chat IDs
========================================================= */

const CHAT_FILE = path.join(
    process.cwd(),
    "chat_ids.json"
);

let chatIds = {
    TASI: [],
    US: [],
    CRYPTO: []
};

function loadChatIds() {

    try {

        if (!fs.existsSync(CHAT_FILE)) {
            return;
        }

        const data = fs.readFileSync(
            CHAT_FILE,
            "utf8"
        );

        const parsed = JSON.parse(data);

        if (parsed && typeof parsed === "object") {
            chatIds = {
                TASI: Array.isArray(parsed.TASI)
                    ? parsed.TASI
                    : [],

                US: Array.isArray(parsed.US)
                    ? parsed.US
                    : [],

                CRYPTO: Array.isArray(parsed.CRYPTO)
                    ? parsed.CRYPTO
                    : []
            };
        }

    } catch (_) {}
}

function saveChatId(
    market,
    chatId
) {

    if (!chatIds[market]) {
        chatIds[market] = [];
    }

    if (!chatIds[market].includes(chatId)) {

        chatIds[market].push(chatId);

        try {

            fs.writeFileSync(
                CHAT_FILE,
                JSON.stringify(
                    chatIds,
                    null,
                    2
                )
            );

        } catch (_) {}
    }
}

loadChatIds();

/* =========================================================
   رسالة الترحيب
========================================================= */

function marketName(market) {

    if (market === "TASI") {
        return "🇸🇦 السوق السعودي";
    }

    if (market === "US") {
        return "🇺🇸 السوق الأمريكي";
    }

    return "🪙 العملات الرقمية";
}

function welcomeText(market) {

    return `
💀🚀 <b>AI PRO MAX</b>

✅ البوت يعمل الآن

🔄 الفحص تلقائي وكامل
⏱️ الفحص كل دقيقتين

📊 <b>السوق:</b>
${marketName(market)}

🧠 <b>المحرك الذكي:</b>

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

📡 <b>مصدر البيانات:</b>
EODHD فقط
`;
}

async function sendWelcome(
    bot,
    market,
    chatId
) {

    try {

        await bot.sendMessage(
            chatId,
            welcomeText(market),
            {
                parse_mode: "HTML"
            }
        );

    } catch (_) {}
}

/* =========================================================
   أدوات EODHD
========================================================= */

function sleep(ms) {

    return new Promise(
        resolve => setTimeout(resolve, ms)
    );
}

function buildUrl(
    endpoint,
    params = {}
) {

    const url = new URL(
        EODHD_BASE + endpoint
    );

    url.searchParams.set(
        "api_token",
        EODHD_API_KEY
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
    params = {}
) {

    if (!EODHD_API_KEY) {
        throw new Error(
            "EODHD_API_KEY غير موجود"
        );
    }

    await sleep(REQUEST_DELAY);

    const url = buildUrl(
        endpoint,
        params
    );

    const response = await fetch(
        url,
        {
            method: "GET",
            headers: {
                "Accept": "application/json"
            }
        }
    );

    const text = await response.text();

    if (!response.ok) {

        throw new Error(
            `EODHD HTTP ${response.status}: ${text.slice(0, 500)}`
        );
    }

    let data;

    try {

        data = JSON.parse(text);

    } catch (_) {

        throw new Error(
            "EODHD أعاد استجابة غير صالحة"
        );
    }

    return data;
}

/* =========================================================
   حالة EODHD
========================================================= */

let eodhdBlockedUntil = 0;

function isEodhdBlocked() {

    return Date.now() < eodhdBlockedUntil;
}

function markEodhdBlocked(
    minutes = 10
) {

    eodhdBlockedUntil =
        Date.now() +
        minutes * 60 * 1000;
}

/* =========================================================
   استخراج الرسالة
========================================================= */

function readableError(error) {

    const text =
        String(
            error &&
            error.message ||
            error
        );

    return text
        .replace(EODHD_API_KEY, "***");
}

/* =========================================================
   قائمة البورصات
========================================================= */

let discoveredTasiExchange = null;

async function findTasiExchange() {

    if (discoveredTasiExchange) {
        return discoveredTasiExchange;
    }

    const rows = await eodhd(
        "exchanges-list/"
    );

    if (!Array.isArray(rows)) {

        throw new Error(
            "قائمة البورصات من EODHD غير صالحة"
        );
    }

    const candidates = rows.filter(
        row => {

            const text =
                `${row.Name || ""} ${row.Code || ""} ${row.Country || ""}`;

            return /Saudi|Tadawul|Saudi Stock Exchange/i
                .test(text);
        }
    );

    if (!candidates.length) {

        throw new Error(
            "لم يتم العثور على بورصة السعودية من EODHD"
        );
    }

    discoveredTasiExchange =
        candidates[0].Code;

    console.log(
        `TASI Exchange: ${discoveredTasiExchange}`
    );

    return discoveredTasiExchange;
}

/* =========================================================
   قوائم الرموز
========================================================= */

let universe = {
    TASI: [],
    US: [],
    CRYPTO: []
};

let universeLoadedAt = 0;

async function loadExchangeSymbols(
    exchange
) {

    const rows = await eodhd(
        `exchange-symbol-list/${exchange}`
    );

    if (!Array.isArray(rows)) {
        throw new Error(
            `EODHD أعاد قائمة رموز غير صالحة لـ ${exchange}`
        );
    }

    return rows;
}

/* =========================================================
   تحميل TASI
========================================================= */

async function loadTasi() {

    const exchange =
        await findTasiExchange();

    const rows =
        await loadExchangeSymbols(
            exchange
        );

    return rows
        .map(row => {

            const code =
                String(
                    row.Code ||
                    row.code ||
                    ""
                ).trim();

            if (!code) {
                return null;
            }

            return {
                symbol:
                    `${code}.${exchange}`,

                code,

                name:
                    row.Name ||
                    row.name ||
                    code,

                exchange
            };

        })
        .filter(Boolean);
}

/* =========================================================
   تحميل US
========================================================= */

async function loadUS() {

    const rows =
        await loadExchangeSymbols(
            "US"
        );

    return rows
        .map(row => {

            const code =
                String(
                    row.Code ||
                    row.code ||
                    ""
                ).trim();

            if (!code) {
                return null;
            }

            return {
                symbol:
                    `${code}.US`,

                code,

                name:
                    row.Name ||
                    row.name ||
                    code,

                exchange: "US"
            };

        })
        .filter(Boolean);
}

/* =========================================================
   تحميل Crypto
========================================================= */

async function loadCrypto() {

    const rows =
        await loadExchangeSymbols(
            "CC"
        );

    return rows
        .map(row => {

            const code =
                String(
                    row.Code ||
                    row.code ||
                    ""
                ).trim();

            if (!code) {
                return null;
            }

            return {
                symbol:
                    `${code}.CC`,

                code,

                name:
                    row.Name ||
                    row.name ||
                    code,

                exchange: "CC"
            };

        })
        .filter(Boolean);
}

/* =========================================================
   تحميل القوائم مرة واحدة
========================================================= */

async function loadUniverses() {

    if (isEodhdBlocked()) {
        return false;
    }

    if (
        universeLoadedAt &&
        Date.now() - universeLoadedAt <
        60 * 60 * 1000
    ) {
        return true;
    }

    try {

        const tasi =
            await loadTasi();

        const us =
            await loadUS();

        const crypto =
            await loadCrypto();

        universe.TASI =
            tasi;

        universe.US =
            us;

        universe.CRYPTO =
            crypto;

        universeLoadedAt =
            Date.now();

        console.log(
            `TASI symbols: ${tasi.length}`
        );

        console.log(
            `US symbols: ${us.length}`
        );

        console.log(
            `CRYPTO symbols: ${crypto.length}`
        );

        return true;

    } catch (error) {

        const message =
            readableError(error);

        console.log(
            `EODHD: ${message}`
        );

        if (
            message.includes("402") ||
            message.includes("403") ||
            message.includes("429")
        ) {

            markEodhdBlocked(10);
        }

        return false;
    }
}

/* =========================================================
   أسعار السوق
========================================================= */

async function getQuote(
    symbol
) {

    return await eodhd(
        `real-time/${encodeURIComponent(symbol)}`
    );
}

/* =========================================================
   بيانات Intraday
========================================================= */

async function getIntraday(
    symbol
) {

    return await eodhd(
        `intraday/${encodeURIComponent(symbol)}`,
        {
            interval: "5m"
        }
    );
}

/* =========================================================
   تحويل البيانات
========================================================= */

function normalizeBars(
    data
) {

    if (!Array.isArray(data)) {
        return [];
    }

    return data
        .map(row => {

            const close =
                Number(row.close);

            const open =
                Number(row.open);

            const high =
                Number(row.high);

            const low =
                Number(row.low);

            const volume =
                Number(row.volume);

            if (
                !Number.isFinite(close) ||
                !Number.isFinite(high) ||
                !Number.isFinite(low)
            ) {
                return null;
            }

            return {
                open,
                high,
                low,
                close,
                volume:
                    Number.isFinite(volume)
                        ? volume
                        : 0
            };

        })
        .filter(Boolean);
}

/* =========================================================
   EMA
========================================================= */

function ema(
    values,
    period
) {

    if (
        !Array.isArray(values) ||
        values.length < period
    ) {
        return NaN;
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
            Number(values[i]);
    }

    result /= period;

    for (
        let i = period;
        i < values.length;
        i++
    ) {

        result =
            (
                Number(values[i]) -
                result
            ) *
            multiplier +
            result;
    }

    return result;
}

/* =========================================================
   RSI
========================================================= */

function rsi(
    values,
    period = 14
) {

    if (
        !Array.isArray(values) ||
        values.length <= period
    ) {
        return NaN;
    }

    let gains = 0;
    let losses = 0;

    for (
        let i = 1;
        i <= period;
        i++
    ) {

        const diff =
            values[i] -
            values[i - 1];

        if (diff >= 0) {
            gains += diff;
        } else {
            losses += Math.abs(diff);
        }
    }

    let avgGain =
        gains / period;

    let avgLoss =
        losses / period;

    for (
        let i = period + 1;
        i < values.length;
        i++
    ) {

        const diff =
            values[i] -
            values[i - 1];

        const gain =
            diff > 0 ? diff : 0;

        const loss =
            diff < 0
                ? Math.abs(diff)
                : 0;

        avgGain =
            (
                avgGain *
                (period - 1) +
                gain
            ) / period;

        avgLoss =
            (
                avgLoss *
                (period - 1) +
                loss
            ) / period;
    }

    if (avgLoss === 0) {
        return 100;
    }

    const rs =
        avgGain / avgLoss;

    return 100 - (100 / (1 + rs));
}

/* =========================================================
   ATR
========================================================= */

function atr(
    bars,
    period = 14
) {

    if (
        !Array.isArray(bars) ||
        bars.length <= period
    ) {
        return NaN;
    }

    const trs = [];

    for (
        let i = 1;
        i < bars.length;
        i++
    ) {

        const current =
            bars[i];

        const previous =
            bars[i - 1];

        const tr =
            Math.max(
                current.high -
                    current.low,

                Math.abs(
                    current.high -
                    previous.close
                ),

                Math.abs(
                    current.low -
                    previous.close
                )
            );

        trs.push(tr);
    }

    if (trs.length < period) {
        return NaN;
    }

    let value = 0;

    for (
        let i = 0;
        i < period;
        i++
    ) {

        value += trs[i];
    }

    value /= period;

    for (
        let i = period;
        i < trs.length;
        i++
    ) {

        value =
            (
                value *
                (period - 1) +
                trs[i]
            ) / period;
    }

    return value;
}

/* =========================================================
   دعم ومقاومة
========================================================= */

function supportResistance(
    bars
) {

    if (
        !Array.isArray(bars) ||
        bars.length < 20
    ) {

        return {
            support: NaN,
            resistance: NaN
        };
    }

    const recent =
        bars.slice(-30);

    let support =
        Infinity;

    let resistance =
        -Infinity;

    for (const bar of recent) {

        if (bar.low < support) {
            support = bar.low;
        }

        if (bar.high > resistance) {
            resistance = bar.high;
        }
    }

    return {
        support,
        resistance
    };
}

/* =========================================================
   قوة الحجم
========================================================= */

function volumeStrength(
    bars
) {

    if (
        !Array.isArray(bars) ||
        bars.length < 21
    ) {
        return 1;
    }

    const recent =
        bars.slice(-20);

    const volumes =
        recent
            .map(x => x.volume)
            .filter(
                x =>
                    Number.isFinite(x) &&
                    x > 0
            );

    if (!volumes.length) {
        return 1;
    }

    const average =
        volumes.reduce(
            (a, b) => a + b,
            0
        ) / volumes.length;

    const latest =
        Number(
            bars[bars.length - 1].volume
        );

    if (!average || !latest) {
        return 1;
    }

    return latest / average;
}

/* =========================================================
   قوة الشراء والبيع
========================================================= */

function buySellPower(
    bars
) {

    if (
        !Array.isArray(bars) ||
        bars.length < 2
    ) {

        return {
            buy: 50,
            sell: 50
        };
    }

    const recent =
        bars.slice(-20);

    let buy = 0;
    let sell = 0;

    for (const bar of recent) {

        const range =
            bar.high - bar.low;

        if (range <= 0) {
            continue;
        }

        const position =
            (
                bar.close -
                bar.low
            ) / range;

        const weight =
            Math.max(
                1,
                bar.volume || 1
            );

        buy +=
            position *
            weight;

        sell +=
            (1 - position) *
            weight;
    }

    if (
        buy <= 0 &&
        sell <= 0
    ) {

        return {
            buy: 50,
            sell: 50
        };
    }

    const total =
        buy + sell;

    return {
        buy:
            Math.round(
                (buy / total) * 100
            ),

        sell:
            Math.round(
                (sell / total) * 100
            )
    };
}

/* =========================================================
   اتجاه السوق
========================================================= */

function trendState(
    price,
    ema8,
    ema21,
    ema50
) {

    if (
        price > ema8 &&
        ema8 > ema21 &&
        ema21 > ema50
    ) {

        return "صاعد قوي";
    }

    if (
        price > ema21 &&
        ema21 > ema50
    ) {

        return "صاعد";
    }

    if (
        price < ema8 &&
        ema8 < ema21 &&
        ema21 < ema50
    ) {

        return "هابط قوي";
    }

    if (
        price < ema21 &&
        ema21 < ema50
    ) {

        return "هابط";
    }

    return "محايد";
}

/* =========================================================
   حساب قوة الإشارة
========================================================= */

function calculateSignal(
    price,
    ema8,
    ema21,
    ema50,
    rsi14,
    volume,
    buyPower,
    sellPower,
    support,
    resistance
) {

    let buyScore = 0;
    let sellScore = 0;

    /* الاتجاه */

    if (
        price > ema8
    ) buyScore += 10;

    if (
        ema8 > ema21
    ) buyScore += 10;

    if (
        ema21 > ema50
    ) buyScore += 10;

    if (
        price < ema8
    ) sellScore += 10;

    if (
        ema8 < ema21
    ) sellScore += 10;

    if (
        ema21 < ema50
    ) sellScore += 10;

    /* RSI */

    if (
        rsi14 >= 50 &&
        rsi14 <= 75
    ) {
        buyScore += 15;
    }

    if (
        rsi14 <= 50 &&
        rsi14 >= 25
    ) {
        sellScore += 15;
    }

    /* الحجم */

    if (volume >= 1.5) {

        buyScore += 10;
        sellScore += 10;
    }

    if (volume >= 2) {

        buyScore += 5;
        sellScore += 5;
    }

    /* قوة الشراء */

    if (
        buyPower >= 65
    ) {
        buyScore += 15;
    }

    if (
        sellPower >= 65
    ) {
        sellScore += 15;
    }

    /* الدعم */

    if (
        Number.isFinite(support) &&
        price > support &&
        price <=
            support +
            Math.abs(price * 0.03)
    ) {

        buyScore += 10;
    }

    /* المقاومة */

    if (
        Number.isFinite(resistance) &&
        price < resistance &&
        price >=
            resistance -
            Math.abs(price * 0.03)
    ) {

        sellScore += 10;
    }

    const buy =
        Math.min(
            100,
            buyScore
        );

    const sell =
        Math.min(
            100,
            sellScore
        );

    if (
        buy >= MIN_SIGNAL_SCORE &&
        buy > sell + 8
    ) {

        return {
            signal: "BUY",
            score: buy
        };
    }

    if (
        sell >= MIN_SIGNAL_SCORE &&
        sell > buy + 8
    ) {

        return {
            signal: "SELL",
            score: sell
        };
    }

    return {
        signal: "NONE",
        score:
            Math.max(
                buy,
                sell
            )
    };
}

/* =========================================================
   أهداف ATR
========================================================= */

function makeTargets(
    price,
    atrValue,
    signal
) {

    const targets = [];

    if (
        !Number.isFinite(price) ||
        !Number.isFinite(atrValue) ||
        atrValue <= 0
    ) {
        return targets;
    }

    /*
       أهداف متدرجة من ATR
    */

    const multipliers = [
        0.5,
        1.0,
        1.5,
        2.0,
        2.5,
        3.0,
        3.5,
        4.0
    ];

    for (
        let i = 0;
        i < multipliers.length;
        i++
    ) {

        const m =
            multipliers[i];

        const target =
            signal === "BUY"
                ? price + atrValue * m
                : price - atrValue * m;

        const percentage =
            (
                (target - price) /
                price
            ) * 100;

        targets.push({

            number: i + 1,

            price: target,

            percentage:
                percentage
        });
    }

    return targets;
}

/* =========================================================
   تنسيق الأرقام
========================================================= */

function decimals(
    value
) {

    if (!Number.isFinite(value)) {
        return "—";
    }

    if (
        Math.abs(value) >= 1000
    ) {
        return value.toLocaleString(
            "en-US",
            {
                maximumFractionDigits: 2
            }
        );
    }

    if (
        Math.abs(value) >= 1
    ) {
        return value.toFixed(2);
    }

    return value.toFixed(4);
}

function money(
    value
) {

    return decimals(value);
}

function pct(
    value
) {

    if (!Number.isFinite(value)) {
        return "—";
    }

    return (
        value >= 0
            ? "+"
            : ""
    ) +
        value.toFixed(2) +
        "%";
}

function volumeText(
    value
) {

    if (
        !Number.isFinite(value)
    ) {
        return "—";
    }

    if (
        value >= 1e9
    ) {

        return (
            value / 1e9
        ).toFixed(2) + "B";
    }

    if (
        value >= 1e6
    ) {

        return (
            value / 1e6
        ).toFixed(2) + "M";
    }

    if (
        value >= 1e3
    ) {

        return (
            value / 1e3
        ).toFixed(2) + "K";
    }

    return String(
        Math.round(value)
    );
}

/* =========================================================
   التحليل الكامل
========================================================= */

async function analyzeSymbol(
    item
) {

    const quote =
        await getQuote(
            item.symbol
        );

    const price =
        Number(
            quote.close ??
            quote.price ??
            quote.last
        );

    if (
        !Number.isFinite(price) ||
        price <= 0
    ) {

        return null;
    }

    /* US minimum */

    if (
        item.exchange === "US" &&
        price < MIN_US_PRICE
    ) {

        return null;
    }

    const barsRaw =
        await getIntraday(
            item.symbol
        );

    const bars =
        normalizeBars(
            barsRaw
        );

    if (
        bars.length < 60
    ) {

        return null;
    }

    const closes =
        bars.map(
            x => x.close
        );

    const ema8 =
        ema(
            closes,
            EMA_FAST
        );

    const ema21 =
        ema(
            closes,
            EMA_MID
        );

    const ema50 =
        ema(
            closes,
            EMA_SLOW
        );

    const rsi14 =
        rsi(
            closes,
            RSI_PERIOD
        );

    const atr14 =
        atr(
            bars,
            ATR_PERIOD
        );

    const sr =
        supportResistance(
            bars
        );

    const volume =
        volumeStrength(
            bars
        );

    const power =
        buySellPower(
            bars
        );

    const signal =
        calculateSignal(
            price,
            ema8,
            ema21,
            ema50,
            rsi14,
            volume,
            power.buy,
            power.sell,
            sr.support,
            sr.resistance
        );

    if (
        signal.signal === "NONE"
    ) {

        return null;
    }

    const change =
        Number(
            quote.change_p ??
            quote.change ??
            0
        );

    const targets =
        makeTargets(
            price,
            atr14,
            signal.signal
        );

    return {

        market:
            item.exchange === "SR"
                ? "TASI"
                : item.exchange === "US"
                    ? "US"
                    : "CRYPTO",

        symbol:
            item.symbol,

        name:
            item.name,

        price,

        change,

        signal:
            signal.signal,

        score:
            signal.score,

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

        volume:
            Number(
                quote.volume ||
                quote.volumeToday ||
                0
            ),

        buyPower:
            power.buy,

        sellPower:
            power.sell,

        trend:
            trendState(
                price,
                ema8,
                ema21,
                ema50
            ),

        targets
    };
}

/* =========================================================
   ترتيب المرشحين
========================================================= */

async function collectCandidates(
    market
) {

    const list =
        universe[market] || [];

    if (!list.length) {
        return [];
    }

    const candidates = [];

    /*
       نقرأ الأسعار أولًا.
       لا نعمل التحليل الثقيل لكل سهم
       حتى لا نستهلك API بشكل غير ضروري.
    */

    for (
        let i = 0;
        i < list.length;
        i++
    ) {

        if (isEodhdBlocked()) {
            break;
        }

        const item =
            list[i];

        try {

            const quote =
                await getQuote(
                    item.symbol
                );

            const price =
                Number(
                    quote.close ??
                    quote.price ??
                    quote.last
                );

            if (
                !Number.isFinite(price) ||
                price <= 0
            ) {
                continue;
            }

            if (
                market === "US" &&
                price < MIN_US_PRICE
            ) {
                continue;
            }

            const change =
                Number(
                    quote.change_p ??
                    quote.change ??
                    0
                );

            const volume =
                Number(
                    quote.volume ||
                    quote.volumeToday ||
                    0
                );

            candidates.push({

                ...item,

                price,

                change,

                volume
            });

        } catch (error) {

            const message =
                readableError(error);

            if (
                message.includes("402") ||
                message.includes("403") ||
                message.includes("429")
            ) {

                markEodhdBlocked(10);

                break;
            }
        }
    }

    /*
       نأخذ الأسهم الأكثر حركة أولًا.
    */

    candidates.sort(
        (a, b) =>
            Math.abs(b.change) -
            Math.abs(a.change)
    );

    return candidates.slice(
        0,
        MAX_DEEP_ANALYSIS
    );
}

/* =========================================================
   منع التكرار
========================================================= */

const lastAlerts =
    new Map();

function alertKey(
    signal
) {

    return (
        signal.market +
        "|" +
        signal.symbol +
        "|" +
        signal.signal
    );
}

function shouldAlert(
    signal
) {

    const key =
        alertKey(signal);

    const last =
        lastAlerts.get(key) || 0;

    if (
        Date.now() - last <
        ALERT_COOLDOWN
    ) {

        return false;
    }

    lastAlerts.set(
        key,
        Date.now()
    );

    return true;
}

/* =========================================================
   السهم المتحرك
========================================================= */

const UP_FRAMES = [
    "🟢⬆️",
    "🟢↗️",
    "🟢⬆️",
    "🟢↗️"
];

const DOWN_FRAMES = [
    "🔴⬇️",
    "🔴↘️",
    "🔴⬇️",
    "🔴↘️"
];

function signalBadge(
    signal,
    frame
) {

    if (signal === "BUY") {

        return (
            `${UP_FRAMES[frame % UP_FRAMES.length]} ` +
            `<b>شراء قوي</b>`
        );
    }

    return (
        `${DOWN_FRAMES[frame % DOWN_FRAMES.length]} ` +
        `<b>بيع قوي</b>`
    );
}

/* =========================================================
   رسالة الإشارة
========================================================= */

function signalMessage(
    signal,
    frame = 0
) {

    const isBuy =
        signal.signal === "BUY";

    const market =
        marketName(
            signal.market
        );

    const targets =
        signal.targets
            .map(
                target =>
`TP${target.number}   <b>${money(target.price)}</b>   (${pct(target.percentage)})`
            )
            .join("\n");

    const changeText =
        pct(signal.change);

    const trendIcon =
        isBuy
            ? "📈"
            : "📉";

    return `
💀🚀 <b>AI PRO MAX SIGNAL</b>

${market}

<b>${signal.symbol}</b>
${signal.name || ""}

${signalBadge(
    signal.signal,
    frame
)}

━━━━━━━━━━━━━━━━━━

💰 السعر:
<b>${money(signal.price)}</b>

📊 التغير:
<b>${changeText}</b>

🧠 قوة الإشارة:
<b>${signal.score}/100</b>

🟢 قوة الشراء:
<b>${signal.buyPower}%</b>

🔴 قوة البيع:
<b>${signal.sellPower}%</b>

📦 قوة الحجم:
<b>${signal.volumeStrength.toFixed(2)}x</b>

📊 الحجم:
<b>${volumeText(signal.volume)}</b>

${trendIcon} الاتجاه:
<b>${signal.trend}</b>

━━━━━━━━━━━━━━━━━━

📊 EMA 8:
<b>${money(signal.ema8)}</b>

📊 EMA 21:
<b>${money(signal.ema21)}</b>

📊 EMA 50:
<b>${money(signal.ema50)}</b>

📟 RSI 14:
<b>${signal.rsi14.toFixed(1)}</b>

🔥 ATR 14:
<b>${money(signal.atr14)}</b>

━━━━━━━━━━━━━━━━━━

🟢 الدعم:
<b>${money(signal.support)}</b>

🔴 المقاومة:
<b>${money(signal.resistance)}</b>

━━━━━━━━━━━━━━━━━━

🎯 <b>أهداف ATR الثمانية</b>

${targets}

━━━━━━━━━━━━━━━━━━

🤖 <b>AI PRO MAX</b>
🔄 الفحص تلقائي كل دقيقتين
📡 مصدر البيانات: <b>EODHD فقط</b>
`;
}

/* =========================================================
   إرسال الرسالة + تحريك السهم
========================================================= */

async function sendAnimatedSignal(
    bot,
    chatId,
    signal
) {

    if (!bot || !chatId) {
        return;
    }

    try {

        const message =
            await bot.sendMessage(
                chatId,
                signalMessage(
                    signal,
                    0
                ),
                {
                    parse_mode: "HTML",
                    disable_web_page_preview: true
                }
            );

        /*
           حركة قصيرة للسهم
        */

        for (
            let frame = 1;
            frame < 6;
            frame++
        ) {

            await sleep(1200);

            try {

                await bot.editMessageText(
                    signalMessage(
                        signal,
                        frame
                    ),
                    {
                        chat_id: chatId,
                        message_id:
                            message.message_id,
                        parse_mode: "HTML",
                        disable_web_page_preview: true
                    }
                );

            } catch (_) {}
        }

    } catch (error) {

        console.log(
            "Telegram signal error"
        );
    }
}

/* =========================================================
   إرسال لجميع المشتركين
========================================================= */

async function broadcast(
    market,
    signal
) {

    let bot = null;

    if (market === "TASI") {
        bot = tasiBot;
    }

    if (market === "US") {
        bot = usBot;
    }

    if (market === "CRYPTO") {
        bot = cryptoBot;
    }

    if (!bot) {
        return;
    }

    const ids =
        chatIds[market] || [];

    for (const chatId of ids) {

        await sendAnimatedSignal(
            bot,
            chatId,
            signal
        );
    }
}

/* =========================================================
   فحص سوق واحد
========================================================= */

let marketBusy = {
    TASI: false,
    US: false,
    CRYPTO: false
};

async function scanMarket(
    market
) {

    if (
        marketBusy[market]
    ) {
        return;
    }

    marketBusy[market] = true;

    try {

        console.log(
            `${market}: بدء الفحص`
        );

        const candidates =
            await collectCandidates(
                market
            );

        if (!candidates.length) {

            console.log(
                `${market}: لا توجد مرشحات`
            );

            return;
        }

        const signals = [];

        for (
            const candidate
            of candidates
        ) {

            if (isEodhdBlocked()) {
                break;
            }

            try {

                const result =
                    await analyzeSymbol(
                        candidate
                    );

                if (result) {

                    signals.push(
                        result
                    );
                }

            } catch (error) {

                const message =
                    readableError(error);

                if (
                    message.includes("402") ||
                    message.includes("403") ||
                    message.includes("429")
                ) {

                    markEodhdBlocked(
                        10
                    );

                    break;
                }
            }
        }

        /*
           أقوى الإشارات أولًا
        */

        signals.sort(
            (a, b) =>
                b.score -
                a.score
        );

        /*
           نرسل أقوى إشارة فقط
           لكل سوق في الدورة
           لمنع إغراق Telegram.
        */

        if (signals.length) {

            const strongest =
                signals[0];

            if (
                shouldAlert(
                    strongest
                )
            {

                await broadcast(
                    market,
                    strongest
                );

                console.log(
                    `${market}: تم إرسال ${strongest.symbol}`
                );
            }
        }

    } finally {

        marketBusy[market] = false;
    }
}

/* =========================================================
   دورة الفحص
========================================================= */

let scanRunning = false;

async function fullScan() {

    if (scanRunning) {
        return;
    }

    if (!EODHD_API_KEY) {
        return;
    }

    if (isEodhdBlocked()) {
        console.log(
            "EODHD: الانتظار قبل إعادة الطلب"
        );

        return;
    }

    scanRunning = true;

    try {

        const loaded =
            await loadUniverses();

        if (!loaded) {
            return;
        }

        /*
           الأسواق تعمل بالتتابع
           حتى لا نضرب API في وقت واحد.
        */

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

        console.log(
            readableError(error)
        );

    } finally {

        scanRunning = false;
    }
}

/* =========================================================
   تشغيل تلقائي
========================================================= */

console.log("");
console.log("==============================================");
console.log("🤖 AI PRO MAX بدأ التشغيل");
console.log("🔄 الفحص تلقائي");
console.log("⏱️ كل دقيقتين");
console.log("📡 EODHD فقط");
console.log("==============================================");
console.log("");

/*
   نبدأ بعد فترة قصيرة
   حتى تكتمل عملية Telegram.
*/

setTimeout(
    () => {

        fullScan();

    },
    5000
);

/*
   كل دقيقتين
*/

setInterval(
    () => {

        fullScan();

    },
    SCAN_INTERVAL
);

/* =========================================================
   إغلاق آمن
========================================================= */

async function shutdown() {

    console.log(
        "إيقاف AI PRO MAX"
    );

    try {

        if (tasiBot) {
            await tasiBot.stopPolling();
        }

        if (usBot) {
            await usBot.stopPolling();
        }

        if (cryptoBot) {
            await cryptoBot.stopPolling();
        }

    } catch (_) {}

    process.exit(0);
}

process.on(
    "SIGTERM",
    shutdown
);

process.on(
    "SIGINT",
    shutdown
);

/* =========================================================
   نهاية الملف
========================================================= */