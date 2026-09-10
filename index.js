
// ============================================================
// 🤖 AI PRO MAX — DUAL AUTONOMOUS STOCK SCANNER
// 🇺🇸 US + 🇸🇦 TASI
// Live Fast Scanner — Every 60 Seconds
// Node.js 18+
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// 🔐 مفاتيح Railway
// ============================================================

const TASI_TOKEN = process.env.||TASI_TOKEN"";
const US_TOKEN = process.env.||US_TOKEN"";

const PORT = Number(process.env.PORT || 3000);

// ============================================================
// ⚙️ إعدادات البوت السعودي
// ============================================================

const TASI_CONFIG = {
    enabled: true,

    name: "AI PRO MAX 🇸🇦 TASI",

    exchange: "SR",

    // قوة الإشارة للتصنيف فقط
    signalScore: 60,

    // الفحص كل دقيقة
    updateIntervalMs: 60 * 1000,

    // دفعة EODHD
    batchSize: 20,

    // لا يوجد حد قوة يمنع الإرسال
    blockWeakSignals: false,

    // إرسال الإشارة أثناء الفحص
    instantAlerts: true
};

// ============================================================
// ⚙️ إعدادات البوت الأمريكي
// ============================================================

const US_CONFIG = {
    enabled: true,

    name: "AI PRO MAX 🇺🇸 US",

    exchange: "US",

    // أقل سعر أمريكي
    minPrice: 0.20,

    // قوة الإشارة للتصنيف فقط
    signalScore: 60,

    // فحص كل دقيقة
    updateIntervalMs: 60 * 1000,

    // لا يوجد شرط قوة يمنع الإرسال
    blockWeakSignals: false,

    // إرسال فور اكتشاف الإشارة
    instantAlerts: true
};

// ============================================================
// ⚙️ إعدادات EODHD
// ============================================================

const EODHD_CONFIG = {
    baseUrl: "https://eodhd.com/api",

    timeoutMs: 20000,

    // Live API يحدث تقريبًا كل دقيقة
    refreshSeconds: 60
};

// ============================================================
// 🌐 Express
// ============================================================

const app = express();

app.use(express.json());

app.get("/", (req, res) => {
    res.status(200).send(
        "AI PRO MAX — US + TASI LIVE SCANNER ONLINE"
    );
});

app.get("/health", (req, res) => {
    res.json({
        status: "online",
        time: new Date().toISOString(),
        us: US_CONFIG.enabled,
        tasi: TASI_CONFIG.enabled,
        scanner: "LIVE",
        interval: "60 seconds"
    });
});

app.listen(PORT, () => {
    console.log("==============================================");
    console.log("🚀 AI PRO MAX SCANNER ONLINE");
    console.log("🌐 PORT:", PORT);
    console.log("🇺🇸 US:", US_CONFIG.enabled);
    console.log("🇸🇦 TASI:", TASI_CONFIG.enabled);
    console.log("⚡ LIVE SCAN: كل 60 ثانية");
    console.log("==============================================");
});

// ============================================================
// 🧠 أدوات عامة
// ============================================================

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function num(v, fallback = 0) {
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
}

function round(v, digits = 2) {
    return Number(num(v).toFixed(digits));
}

function formatNumber(v) {
    const n = num(v);

    if (!n) return "0";

    if (n >= 1_000_000_000) {
        return (n / 1_000_000_000).toFixed(2) + "B";
    }

    if (n >= 1_000_000) {
        return (n / 1_000_000).toFixed(2) + "M";
    }

    if (n >= 1_000) {
        return (n / 1_000).toFixed(2) + "K";
    }

    return Math.round(n).toLocaleString("en-US");
}

function escapeHtml(text) {
    return String(text ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

// ============================================================
// 🌐 طلب EODHD
// ============================================================

async function eodhdFetch(url) {

    const controller = new AbortController();

    const timeout = setTimeout(() => {
        controller.abort();
    }, EODHD_CONFIG.timeoutMs);

    try {

        const response = await fetch(url, {
            method: "GET",
            headers: {
                "Accept": "application/json",
                "User-Agent": "AI-PRO-MAX-SCANNER/1.0"
            },
            signal: controller.signal
        });

        const text = await response.text();

        if (!response.ok) {

            throw new Error(
                `EODHD HTTP ${response.status}: ${text.slice(0, 300)}`
            );
        }

        try {
            return JSON.parse(text);
        } catch {
            throw new Error("EODHD returned invalid JSON");
        }

    } finally {

        clearTimeout(timeout);
    }
}

// ============================================================
// 🇺🇸 US — LIVE BULK
// ============================================================

async function getUSLiveMarket() {

    const url =
        `${EODHD_CONFIG.baseUrl}/real-time/AAPL.US` +
        `?ex=US` +
        `&api_token=${encodeURIComponent(EODHD_API_KEY)}` +
        `&fmt=json`;

    console.log("🇺🇸 تحميل LIVE MARKET الأمريكي...");

    const data = await eodhdFetch(url);

    if (!Array.isArray(data)) {

        throw new Error(
            "US LIVE BULK لم يرجع Array"
        );
    }

    console.log(
        `🇺🇸 LIVE US: ${data.length.toLocaleString()} سهم`
    );

    return data;
}

// ============================================================
// 🇸🇦 TASI — قائمة الأسهم
// ============================================================

let tasiSymbolsCache = null;

async function getTasiSymbols() {

    if (tasiSymbolsCache && tasiSymbolsCache.length) {
        return tasiSymbolsCache;
    }

    const url =
        `${EODHD_CONFIG.baseUrl}/exchange-symbol-list/SR` +
        `?api_token=${encodeURIComponent(EODHD_API_KEY)}` +
        `&fmt=json` +
        `&type=common_stock`;

    console.log("🇸🇦 تحميل قائمة أسهم تاسي...");

    const data = await eodhdFetch(url);

    if (!Array.isArray(data)) {
        throw new Error("قائمة تاسي غير صحيحة");
    }

    tasiSymbolsCache = data
        .map(item => item.Code)
        .filter(Boolean);

    console.log(
        `🇸🇦 عدد أسهم تاسي: ${tasiSymbolsCache.length}`
    );

    return tasiSymbolsCache;
}

// ============================================================
// 🇸🇦 TASI — LIVE دفعات
// ============================================================

async function getTasiLiveBatch(symbols) {

    if (!symbols.length) {
        return [];
    }

    const first = symbols[0];

    const additional = symbols
        .slice(1)
        .join(",");

    let url =
        `${EODHD_CONFIG.baseUrl}/real-time/${encodeURIComponent(first)}.SR` +
        `?api_token=${encodeURIComponent(EODHD_API_KEY)}` +
        `&fmt=json`;

    if (additional) {
        url += `&s=${encodeURIComponent(additional)}`;
    }

    const data = await eodhdFetch(url);

    if (Array.isArray(data)) {
        return data;
    }

    if (data && typeof data === "object") {
        return [data];
    }

    return [];
}

// ============================================================
// 📊 حساب قوة الإشارة
// ============================================================

function calculateSignalScore(q) {

    const price = num(q.close);
    const open = num(q.open);
    const high = num(q.high);
    const low = num(q.low);
    const change = num(q.change_p);

    if (!price) {
        return 60;
    }

    let score = 60;

    // الحركة اليومية
    score += Math.min(Math.abs(change) * 2, 20);

    // موقع السعر داخل نطاق اليوم
    if (high > low) {

        const position =
            ((price - low) / (high - low)) * 100;

        if (position >= 80 || position <= 20) {
            score += 8;
        }
    }

    // اتجاه الجلسة
    if (open > 0) {

        const sessionMove =
            ((price - open) / open) * 100;

        if (Math.abs(sessionMove) >= 1) {
            score += 5;
        }
    }

    return Math.max(
        1,
        Math.min(100, Math.round(score))
    );
}

// ============================================================
// 📈 تحديد الإشارة
// ============================================================

function getSignal(q) {

    const change = num(q.change_p);

    if (change > 0) {

        if (change >= 5) {
            return {
                type: "EXPLOSION_UP",
                emoji: "💀🚀",
                text: "انفجار صعود"
            };
        }

        if (change >= 2) {
            return {
                type: "STRONG_UP",
                emoji: "🔥🚀",
                text: "صعود قوي"
            };
        }

        return {
            type: "UP",
            emoji: "🟢",
            text: "صعود"
        };
    }

    if (change < 0) {

        if (change <= -5) {
            return {
                type: "EXPLOSION_DOWN",
                emoji: "💀🔻",
                text: "انفجار هبوط"
            };
        }

        if (change <= -2) {
            return {
                type: "STRONG_DOWN",
                emoji: "🔴📉",
                text: "هبوط قوي"
            };
        }

        return {
            type: "DOWN",
            emoji: "🔴",
            text: "هبوط"
        };
    }

    return {
        type: "NEUTRAL",
        emoji: "⚪",
        text: "مستقر"
    };
}

// ============================================================
// 🎯 الأهداف السريعة
// ============================================================

function calculateTargets(price, high, low, direction) {

    price = num(price);

    if (!price) {
        return [];
    }

    const range = Math.max(
        Math.abs(num(high) - num(low)),
        price * 0.01
    );

    const multipliers = [
        0.50,
        0.75,
        1.00,
        1.25,
        1.50,
        2.00,
        2.50,
        3.00
    ];

    return multipliers.map((m, i) => {

        let target;

        if (direction === "UP") {
            target = price + range * m;
        } else {
            target = price - range * m;
        }

        target = Math.max(target, 0.0001);

        return {
            number: i + 1,
            price: round(target, price < 1 ? 4 : 2)
        };
    });
}

// ============================================================
// 📲 رسالة الإشارة
// ============================================================

function buildMessage(q, market) {

    const code =
        q.code ||
        q.Code ||
        "UNKNOWN";

    const price =
        num(q.close);

    const change =
        num(q.change_p);

    const signal =
        getSignal(q);

    const score =
        calculateSignalScore(q);

    let direction =
        change >= 0 ? "UP" : "DOWN";

    const targets =
        calculateTargets(
            price,
            q.high,
            q.low,
            direction
        );

    const targetText =
        targets
            .map(t =>
                `${t.number}️⃣ ${t.price}`
            )
            .join("\n");

    const volume =
        formatNumber(q.volume);

    const previousClose =
        num(q.previousClose);

    const open =
        num(q.open);

    const high =
        num(q.high);

    const low =
        num(q.low);

    const changeText =
        change >= 0
            ? `+${change.toFixed(2)}%`
            : `${change.toFixed(2)}%`;

    const marketName =
        market === "US"
            ? "🇺🇸 السوق الأمريكي"
            : "🇸🇦 السوق السعودي";

    return `
${signal.emoji} <b>AI PRO MAX</b>

${marketName}

<b>السهم:</b> ${escapeHtml(code)}
<b>السعر:</b> ${price}
<b>التغير:</b> ${changeText}

<b>قوة الإشارة:</b> ${score}/100
<b>التصنيف الأساسي:</b> 60
<b>الإشارة:</b> ${signal.text}

━━━━━━━━━━━━━━━━

<b>📊 بيانات الجلسة</b>

الافتتاح: ${open}
الأعلى: ${high}
الأدنى: ${low}
الإغلاق/السعر الحالي: ${price}
حجم التداول: ${volume}
الإغلاق السابق: ${previousClose}

━━━━━━━━━━━━━━━━

<b>🎯 الأهداف</b>

${targetText}

━━━━━━━━━━━━━━━━

⚡ <b>فحص LIVE سريع</b>
📡 <b>إرسال فوري أثناء الفحص</b>
⏱️ <b>الدورة: كل 60 ثانية</b>
`;
}

// ============================================================
// 🧠 منع تكرار نفس الإشارة داخل نفس الدقيقة فقط
// ============================================================

const lastSent = new Map();

function shouldSend(code, change, market) {

    const key = `${market}:${code}`;

    const currentBucket =
        Math.floor(Date.now() / 60000);

    const state =
        lastSent.get(key);

    const changeRounded =
        Number(num(change).toFixed(2));

    if (
        state &&
        state.bucket === currentBucket &&
        state.change === changeRounded
    ) {
        return false;
    }

    lastSent.set(key, {
        bucket: currentBucket,
        change: changeRounded
    });

    return true;
}

// ============================================================
// 📲 إرسال آمن لتليجرام
// ============================================================

async function safeSend(bot, chatId, message) {

    if (!chatId) {
        return;
    }

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

        console.error(
            "❌ Telegram:",
            error.message
        );
    }
}

// ============================================================
// 🇺🇸 فحص السوق الأمريكي
// ============================================================

let usScanning = false;

async function scanUS(bot, chatId) {

    if (usScanning) {
        console.log("⏳ US scan ما زال يعمل...");
        return;
    }

    usScanning = true;

    try {

        console.log("==============================================");
        console.log("🇺🇸 بدء الفحص الأمريكي LIVE");
        console.log("⚡ بدون Bulk EOD");
        console.log("==============================================");

        const market =
            await getUSLiveMarket();

        let scanned = 0;
        let alerts = 0;

        for (const q of market) {

            scanned++;

            const code =
                q.code ||
                q.Code;

            const price =
                num(q.close);

            const change =
                num(q.change_p);

            if (!code || !price) {
                continue;
            }

            // السعر الأمريكي المطلوب
            if (price < US_CONFIG.minPrice) {
                continue;
            }

            // لا يوجد شرط قوة 60 يمنع الإرسال
            // 60 مجرد تصنيف للإشارة

            const signal =
                getSignal(q);

            // المستقر ليس إشارة تداول
            // ولا يوجد حد لقوة الإشارة
            if (signal.type === "NEUTRAL") {
                continue;
            }

            if (
                !shouldSend(
                    code,
                    change,
                    "US"
                )
            ) {
                continue;
            }

            const message =
                buildMessage(
                    q,
                    "US"
                );

            await safeSend(
                bot,
                chatId,
                message
            );

            alerts++;

            // نترك Telegram يتنفس قليلاً
            await sleep(80);

            if (scanned % 1000 === 0) {

                console.log(
                    `🇺🇸 ${scanned.toLocaleString()} / ${market.length.toLocaleString()} | إشعارات: ${alerts}`
                );
            }
        }

        console.log(
            `🇺🇸 انتهى الفحص | تم فحص: ${scanned.toLocaleString()} | الإشعارات: ${alerts}`
        );

    } catch (error) {

        console.error(
            "❌ US SCAN ERROR:",
            error.message
        );

    } finally {

        usScanning = false;
    }
}

// ============================================================
// 🇸🇦 فحص تاسي
// ============================================================

let tasiScanning = false;

async function scanTASI(bot, chatId) {

    if (tasiScanning) {
        console.log("⏳ TASI scan ما زال يعمل...");
        return;
    }

    tasiScanning = true;

    try {

        console.log("==============================================");
        console.log("🇸🇦 بدء فحص تاسي LIVE");
        console.log("⚡ دفعات سريعة");
        console.log("==============================================");

        const symbols =
            await getTasiSymbols();

        let scanned = 0;
        let alerts = 0;

        for (
            let i = 0;
            i < symbols.length;
            i += TASI_CONFIG.batchSize
        ) {

            const batch =
                symbols.slice(
                    i,
                    i + TASI_CONFIG.batchSize
                );

            let quotes = [];

            try {

                quotes =
                    await getTasiLiveBatch(
                        batch
                    );

            } catch (error) {

                console.error(
                    `❌ TASI batch ${i}:`,
                    error.message
                );

                continue;
            }

            for (const q of quotes) {

                scanned++;

                const code =
                    q.code ||
                    q.Code;

                const price =
                    num(q.close);

                const change =
                    num(q.change_p);

                if (!code || !price) {
                    continue;
                }

                // لا يوجد شرط قوة يمنع الإرسال
                const signal =
                    getSignal(q);

                if (
                    signal.type === "NEUTRAL"
                ) {
                    continue;
                }

                if (
                    !shouldSend(
                        code,
                        change,
                        "TASI"
                    )
                ) {
                    continue;
                }

                const message =
                    buildMessage(
                        q,
                        "TASI"
                    );

                await safeSend(
                    bot,
                    chatId,
                    message
                );

                alerts++;

                await sleep(80);
            }

            console.log(
                `🇸🇦 التقدم: ${Math.min(
                    i + batch.length,
                    symbols.length
                )}/${symbols.length} | إشعارات: ${alerts}`
            );
        }

        console.log(
            `🇸🇦 انتهى الفحص | تم فحص: ${scanned} | الإشعارات: ${alerts}`
        );

    } catch (error) {

        console.error(
            "❌ TASI SCAN ERROR:",
            error.message
        );

    } finally {

        tasiScanning = false;
    }
}

// ============================================================
// 🤖 إنشاء البوتات
// ============================================================

let usBot = null;
let tasiBot = null;

// ============================================================
// 🇺🇸 BOT US
// ============================================================

if (
    US_CONFIG.enabled &&
    US_TOKEN
) {

    usBot =
        new TelegramBot(
            US_TOKEN,
            {
                polling: true
            }
        );

    usBot.on(
        "polling_error",
        error => {

            console.error(
                "🇺🇸 Telegram polling:",
                error.message
            );
        }
    );

    usBot.onText(
        /\/start/,
        async msg => {

            const chatId =
                msg.chat.id;

            await safeSend(
                usBot,
                chatId,
                `
🚀 <b>AI PRO MAX 🇺🇸</b>

تم تشغيل بوت السوق الأمريكي.

⚡ فحص LIVE سريع
⏱️ كل 60 ثانية
📡 الإشعارات أثناء الفحص
🎯 قوة التصنيف: 60
🔓 لا يوجد شرط قوة يمنع الإرسال

أرسل:
<code>/scan</code>
للبدء الآن.
`
            );
        }
    );

    usBot.onText(
        /\/scan/,
        async msg => {

            const chatId =
                msg.chat.id;

            await safeSend(
                usBot,
                chatId,
                "🔍 🇺🇸 بدء فحص السوق الأمريكي LIVE الآن..."
            );

            scanUS(
                usBot,
                chatId
            );
        }
    );

    console.log(
        "✅ 🇺🇸 US Telegram Bot ONLINE"
    );
}

// ============================================================
// 🇸🇦 BOT TASI
// ============================================================

if (
    TASI_CONFIG.enabled &&
    TASI_TOKEN
) {

    tasiBot =
        new TelegramBot(
            TASI_TOKEN,
            {
                polling: true
            }
        );

    tasiBot.on(
        "polling_error",
        error => {

            console.error(
                "🇸🇦 Telegram polling:",
                error.message
            );
        }
    );

    tasiBot.onText(
        /\/start/,
        async msg => {

            const chatId =
                msg.chat.id;

            await safeSend(
                tasiBot,
                chatId,
                `
🚀 <b>AI PRO MAX 🇸🇦</b>

تم تشغيل بوت السوق السعودي.

⚡ فحص LIVE سريع
⏱️ كل 60 ثانية
📡 الإشعارات أثناء الفحص
🎯 قوة التصنيف: 60
🔓 لا يوجد شرط قوة يمنع الإرسال

أرسل:
<code>/scan</code>
للبدء الآن.
`
            );
        }
    );

    tasiBot.onText(
        /\/scan/,
        async msg => {

            const chatId =
                msg.chat.id;

            await safeSend(
                tasiBot,
                chatId,
                "🔍 🇸🇦 بدء فحص تاسي LIVE الآن..."
            );

            scanTASI(
                tasiBot,
                chatId
            );
        }
    );

    console.log(
        "✅ 🇸🇦 TASI Telegram Bot ONLINE"
    );
}

// ============================================================
// 🔁 التشغيل التلقائي — كل دقيقة
// ============================================================

async function automaticUSLoop() {

    if (
        !US_CONFIG.enabled ||
        !usBot
    ) {
        return;
    }

    console.log(
        "🔄 🇺🇸 سيتم فحص الأمريكي كل 60 ثانية"
    );

    while (true) {

        try {

            const chatId =
                process.env.US_CHAT_ID;

            if (chatId) {

                await scanUS(
                    usBot,
                    chatId
                );
            } else {

                console.log(
                    "⚠️ US_CHAT_ID غير موجود — البوت ينتظر /scan"
                );
            }

        } catch (error) {

            console.error(
                "❌ US AUTO:",
                error.message
            );
        }

        await sleep(
            US_CONFIG.updateIntervalMs
        );
    }
}

// ============================================================
// 🔁 TASI AUTO
// ============================================================

async function automaticTasiLoop() {

    if (
        !TASI_CONFIG.enabled ||
        !tasiBot
    ) {
        return;
    }

    console.log(
        "🔄 🇸🇦 سيتم فحص تاسي كل 60 ثانية"
    );

    while (true) {

        try {

            const chatId =
                process.env.TASI_CHAT_ID;

            if (chatId) {

                await scanTASI(
                    tasiBot,
                    chatId
                );

            } else {

                console.log(
                    "⚠️ TASI_CHAT_ID غير موجود — البوت ينتظر /scan"
                );
            }

        } catch (error) {

            console.error(
                "❌ TASI AUTO:",
                error.message
            );
        }

        await sleep(
            TASI_CONFIG.updateIntervalMs
        );
    }
}

// ============================================================
// 🚀 التشغيل
// ============================================================

setTimeout(() => {

    automaticUSLoop();

}, 5000);

setTimeout(() => {

    automaticTasiLoop();

}, 8000);

console.log("🚀 AI PRO MAX — LIVE SCANNER READY");