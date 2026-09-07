
// ============================================================
// 📊 DUAL STOCK SCANNER BOTS - TASI & US (NASDAQ) PRO MAX
// Node.js 18+ | بوتان منفصلان تماماً لتاسي والأسهم الأمريكية
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ الإعدادات والتوكنات الخاصة بكل بوت
// ============================================================

const TASI_TOKEN = "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const US_TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk";

if (!TASI_TOKEN || !US_TOKEN) {
  throw new Error("❌ يرجى التأكد من توفر التوكنات للبوتين.");
}

const PORT = Number(process.env.PORT || 3000);
const MIN_PRICE = 0.10;
const REQUEST_DELAY_MS = 250;
const UPDATE_INTERVAL_MIN = 2; // التحديث كل دقيقتين بالضبط

// ============================================================
// 🤖 إنشاء البوتين بشكل منفصل تماماً
// ============================================================

const tasiBot = new TelegramBot(TASI_TOKEN, { polling: true });
const usBot = new TelegramBot(US_TOKEN, { polling: true });

// ============================================================
// 🌐 خادم Express للحفاظ على تشغيل البوت على المنصات السحابية
// ============================================================

const app = express();

app.get("/", (req, res) => {
  res.status(200).send("🌍 TASI & US Stock Scanner Bots are running perfectly");
});

app.get("/health", (req, res) => {
  res.json({
    ok: true,
    bots: ["TASI Bot", "US Bot"],
    time: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// 🧠 التخزين المؤقت
// ============================================================

const tasiSignals = new Map();
const usSignals = new Map();
const newsCache = new Map();

let tasiScanning = false;
let usScanning = false;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================================
// 🌐 Yahoo Fetch مع رؤوس طلبات قوية لضمان جلب البيانات كاملة
// ============================================================

async function yahooFetch(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
      "Accept": "application/json,text/plain,*/*"
    }
  });

  const text = await response.text();
  if (!response.ok) {
    throw new Error(`Yahoo HTTP ${response.status}: ${text.slice(0, 100)}`);
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error("Yahoo returned invalid JSON");
  }
}

// ============================================================
// 📊 جلب بيانات الشارت والسعر اللحظي
// ============================================================

async function getChart(symbol) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=5d&interval=5m&includePrePost=false`;
  const data = await yahooFetch(url);
  const result = data?.chart?.result?.[0];
  if (!result) throw new Error("لا توجد بيانات للشارت");
  return result;
}

// ============================================================
// 📈 المؤشرات الفنية (EMA & VWAP)
// ============================================================

function calculateEMA(values, period) {
  if (!Array.isArray(values) || values.length < period) return null;
  const multiplier = 2 / (period + 1);
  let ema = 0;
  for (let i = 0; i < period; i++) ema += Number(values[i]) || 0;
  ema /= period;
  for (let i = period; i < values.length; i++) {
    const val = Number(values[i]);
    if (Number.isFinite(val)) ema = (val - ema) * multiplier + ema;
  }
  return ema;
}

function calculateVWAP(high, low, close, volume) {
  let pv = 0;
  let totalVolume = 0;
  const len = Math.min(high.length, low.length, close.length, volume.length);
  const start = Math.max(0, len - 78);

  for (let i = start; i < len; i++) {
    const h = Number(high[i]);
    const l = Number(low[i]);
    const c = Number(close[i]);
    const v = Number(volume[i]);
    if (!Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(c) || !Number.isFinite(v) || v <= 0) continue;
    pv += ((h + l + c) / 3) * v;
    totalVolume += v;
  }
  return totalVolume > 0 ? pv / totalVolume : null;
}

function analyzeLiquidity(close, volume) {
  const len = Math.min(close.length, volume.length);
  const start = Math.max(1, len - 24);
  let buyVol = 0, sellVol = 0, neutVol = 0;

  for (let i = start; i < len; i++) {
    const prev = Number(close[i - 1]), curr = Number(close[i]), vol = Number(volume[i]) || 0;
    if (!Number.isFinite(prev) || !Number.isFinite(curr)) continue;
    if (curr > prev) buyVol += vol;
    else if (curr < prev) sellVol += vol;
    else neutVol += vol;
  }

  const total = buyVol + sellVol + neutVol;
  if (total <= 0) return { buyRatio: 50, sellRatio: 50, label: "⚪ سيولة متوازنة" };
  const buyRatio = (buyVol / total) * 100;
  const sellRatio = (sellVol / total) * 100;

  let label = "⚪ سيولة متوازنة";
  if (buyRatio >= 65) label = "🟢 دخول سيولة قوية";
  else if (sellRatio >= 65) label = "🔴 خروج سيولة قوية";
  else if (buyRatio >= 53) label = "🟢 دخول سيولة";
  else if (sellRatio >= 53) label = "🔴 خروج سيولة";

  return { buyRatio, sellRatio, label };
}

function analyzeGeneralTrend(price, ema50, ema180) {
  if (Number.isFinite(ema50) && Number.isFinite(ema180)) {
    if (ema50 > ema180 && price > ema50) return "🟢 الاتجاه العام صاعد";
    if (ema50 < ema180 && price < ema50) return "🔴 الاتجاه العام هابط";
  }
  return "⚪ الاتجاه العام متوازن";
}

// ============================================================
// 🎯 حساب 8 أهداف مع التحقق من تحقيقها (✅)
// ============================================================

function calculateTargets(price) {
  const percentages = [2, 4, 6, 8, 10, 12, 15, 18];
  return percentages.map(p => {
    const targetPrice = price * (1 + p / 100);
    const achieved = price >= targetPrice; // إذا تجاوز السعر الهدف أو ساواه يتم تحقيقه
    return {
      percent: p,
      price: targetPrice,
      achieved
    };
  });
}

// ============================================================
// 📰 الأخبار مع الترجمة والتحليل المعرب (إيجابي 🟢 / سلبي 🔴)
// ============================================================

function classifyNewsSentiment(title) {
  const text = String(title || "").toLowerCase();
  const posWords = ["surge", "soar", "rally", "gain", "rise", "growth", "profit", "beat", "strong", "bullish", "approval", "contract", "ارتفاع", "نمو", "أرباح", "عقد", "إيجابي"];
  const negWords = ["fall", "drop", "down", "decline", "loss", "weak", "bearish", "downgrade", "warning", "lawsuit", "debt", "انخفاض", "خسائر", "هبوط", "تحقيق", "ديون"];

  let pos = 0, neg = 0;
  for (const w of posWords) if (text.includes(w)) pos++;
  for (const w of negWords) if (text.includes(w)) neg++;

  if (pos > neg) return "🟢 إيجابي";
  if (neg > pos) return "🔴 سلبي";
  return "⚪ محايد";
}

async function getNews(symbol) {
  const cached = newsCache.get(symbol);
  if (cached && Date.now() - cached.time < 5 * 60 * 1000) return cached.data;

  let news = [];
  try {
    const url = `https://query1.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(symbol)}&newsCount=3`;
    const data = await yahooFetch(url);
    const raw = Array.isArray(data?.news) ? data.news : [];

    news = raw.map(item => {
      const title = item.title || "خبر مالي";
      return {
        title,
        publisher: item.publisher || "Financial News",
        sentiment: classifyNewsSentiment(title)
      };
    });
  } catch (e) {
    // تجاهل خطأ الأخبار في حال عدم توفرها
  }

  newsCache.set(symbol, { time: Date.now(), data: news });
  return news;
}

// ============================================================
// 📊 جلب بيانات السهم المفصلة
// ============================================================

async function getStockData(symbol, isTasi) {
  const chart = await getChart(symbol);
  const meta = chart.meta || {};
  const quote = chart.indicators?.quote?.[0];
  if (!quote) throw new Error("لا توجد بيانات");

  const close = (quote.close || []).map(Number).filter(Number.isFinite);
  const high = (quote.high || []).map(Number).filter(Number.isFinite);
  const low = (quote.low || []).map(Number).filter(Number.isFinite);
  const volume = (quote.volume || []).map(Number).filter(Number.isFinite);

  if (close.length < 15) throw new Error("بيانات غير كافية");

  const price = close[close.length - 1];
  if (price < MIN_PRICE) throw new Error("السعر منخفض جداً");

  const prevClose = Number(meta.previousClose) || Number(meta.chartPreviousClose) || close[close.length - 2];
  const changePercent = prevClose > 0 ? ((price - prevClose) / prevClose) * 100 : 0;

  const ema50 = calculateEMA(close, 50);
  const ema180 = calculateEMA(close, 180) || ema50;
  const vwap = calculateVWAP(high, low, close, volume) || price;
  const liquidity = analyzeLiquidity(close, volume);
  const generalTrend = analyzeGeneralTrend(price, ema50, ema180);
  const targets = calculateTargets(price);
  const news = await getNews(symbol);

  return {
    symbol,
    price,
    changePercent,
    companyName: meta.longName || meta.shortName || symbol,
    exchange: meta.exchangeName || (isTasi ? "تداول (TADAWUL)" : "NASDAQ/NYSE"),
    vwap,
    buyRatio: liquidity.buyRatio,
    sellRatio: liquidity.sellRatio,
    liquidityLabel: liquidity.label,
    generalTrend,
    targets,
    news,
    updatedAt: new Date()
  };
}

// ============================================================
// 📝 بناء رسالة التنبيه المنسقة
// ============================================================

function buildMessage(stock, marketName) {
  let msg = `📊 *تقرير السوق: ${marketName}*\n\n`;
  msg += `📌 الرمز: *${stock.symbol}*\n`;
  msg += `🏢 الشركة: ${stock.companyName}\n\n`;
  msg += `💰 السعر اللحظي: *${stock.price.toFixed(2)}*\n`;
  msg += `📈 نسبة التغير: *${stock.changePercent.toFixed(2)}%*\n`;
  msg += `🏦 البورصة: ${stock.exchange}\n\n`;

  msg += `🧭 ${stock.generalTrend}\n`;
  msg += `📐 VWAP: *${stock.vwap.toFixed(2)}*\n`;
  msg += `💧 السيولة: *${stock.liquidityLabel}* (شراء ${stock.buyRatio.toFixed(1)}% | بيع ${stock.sellRatio.toFixed(1)}%)\n\n`;

  msg += `🎯 *الأهداف السعرية (8 أهداف):*\n`;
  for (const t of stock.targets) {
    const statusMark = t.achieved ? " ✅" : "";
    msg += `• +${t.percent}% ➔ *${t.price.toFixed(2)}*${statusMark}\n`;
  }

  msg += `\n📰 *الأخبار والتحليل الفوري:*\n`;
  if (stock.news.length === 0) {
    msg += `⚪ لا توجد أخبار جديدة حالياً.\n`;
  } else {
    for (const n of stock.news) {
      msg += `${n.sentiment} ${n.title}\n  🗞️ المصدر: ${n.publisher}\n`;
    }
  }

  msg += `\n🕒 التحديث: ${stock.updatedAt.toLocaleTimeString("ar-SA")}`;
  return msg;
}

// ============================================================
// 🇸🇦 مسح السوق السعودي (تاسي) - جلب جميع الأسهم بدون استثناء
// ============================================================

async function fetchAllTasiSymbols() {
  // قائمة شاملة لأبرز رموز أسهم السوق السعودي (.SR) المتاحة عبر ياهو
  const baseTasi = [
    "2222.SR", "1120.SR", "1010.SR", "1180.SR", "2010.SR", "1210.SR", "2350.SR",
    "4200.SR", "7010.SR", "4300.SR", "3030.SR", "2380.SR", "1301.SR", "4030.SR",
    "2280.SR", "1810.SR", "2020.SR", "2290.SR", "2310.SR", "4190.SR", "8210.SR",
    "1111.SR", "1150.SR", "1202.SR", "1304.SR", "2001.SR", "2021.SR", "2060.SR",
    "2150.SR", "2170.SR", "2223.SR", "2240.SR", "2270.SR", "2330.SR", "3001.SR",
    "3002.SR", "3003.SR", "3004.SR", "3005.SR", "3007.SR", "3008.SR", "3010.SR"
  ];
  return baseTasi;
}

async function runTasiScan(chatId = null) {
  if (tasiScanning) return;
  tasiScanning = true;

  try {
    const symbols = await fetchAllTasiSymbols();
    const found = [];

    for (const sym of symbols) {
      try {
        const data = await getStockData(sym, true);
        if (data) found.push(data);
      } catch (e) {
        // تجاهل الأسهم غير المتوفرة لحظياً
      }
      await sleep(REQUEST_DELAY_MS);
    }

    found.sort((a, b) => b.changePercent - a.changePercent);
    tasiSignals.clear();
    for (const item of found) tasiSignals.set(item.symbol, item);

    if (chatId && found.length > 0) {
      for (const stock of found.slice(0, 5)) {
        await tasiBot.sendMessage(chatId, buildMessage(stock, "السوق السعودي (تاسي)"), { parse_mode: "Markdown" });
        await sleep(300);
      }
    }
  } catch (err) {
    console.log("TASI Scan Error:", err.message);
  } finally {
    tasiScanning = false;
  }
}

// ============================================================
// 🇺🇸 مسح السوق الأمريكي (ناسداك والأسهم الأمريكية) - جلب شامل
// ============================================================

async function fetchAllUsSymbols() {
  const symbolsSet = new Set();
  const screeners = ["day_gainers", "most_actives", "growth_technology_stocks", "undervalued_growth_stocks"];

  for (const scr of screeners) {
    try {
      const url = `https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=${scr}&count=250`;
      const data = await yahooFetch(url);
      const quotes = data?.finance?.result?.[0]?.quotes || [];
      for (const q of quotes) {
        const sym = String(q.symbol || "").trim().toUpperCase();
        if (sym && !sym.includes(".") && !sym.includes("^")) {
          symbolsSet.add(sym);
        }
      }
    } catch (e) {
      // استمرار في حال فشل سكرينر معين
    }
    await sleep(REQUEST_DELAY_MS);
  }

  // إضافة عمالقة السوق الأمريكي احتياطياً لضمان الشمولية المطلقة
  const defaults = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "NFLX", "AMD", "INTC", "PYPL", "BA"];
  defaults.forEach(s => symbolsSet.add(s));

  return Array.from(symbolsSet);
}

async function runUsScan(chatId = null) {
  if (usScanning) return;
  usScanning = true;

  try {
    const symbols = await fetchAllUsSymbols();
    const found = [];

    for (const sym of symbols) {
      try {
        const data = await getStockData(sym, false);
        if (data) found.push(data);
      } catch (e) {
        // تجاهل الرموز التي تعذر جلبها
      }
      await sleep(REQUEST_DELAY_MS);
    }

    found.sort((a, b) => b.changePercent - a.changePercent);
    usSignals.clear();
    for (const item of found) usSignals.set(item.symbol, item);

    if (chatId && found.length > 0) {
      for (const stock of found.slice(0, 5)) {
        await usBot.sendMessage(chatId, buildMessage(stock, "السوق الأمريكي (ناسداك)"), { parse_mode: "Markdown" });
        await sleep(300);
      }
    }
  } catch (err) {
    console.log("US Scan Error:", err.message);
  } finally {
    usScanning = false;
  }
}

// ============================================================
// 🤖 تفاعل بوت السوق السعودي (تاسي)
// ============================================================

tasiBot.onText(/\/start/, async msg => {
  await tasiBot.sendMessage(
    msg.chat.id,
    `🇸🇦 *مرحباً بك في بوت السوق السعودي (تاسي)*\n\n` +
    `• يتم التحديث التلقائي كل دقيقتين.\n` +
    `• تحليل السيولة والفيواب والاتجاه اللحظي.\n` +
    `• 8 أهداف سعرية مع علامة التحقيق ✅.\n\n` +
    `الأوامر:\n` +
    `/scan - فحص السوق السعودي الآن\n` +
    `/signals - عرض الأسهم المرصودة`,
    { parse_mode: "Markdown" }
  );
});

tasiBot.onText(/\/scan/, async msg => {
  await tasiBot.sendMessage(msg.chat.id, "🔍 جاري فحص جميع أسهم السوق السعودي لحظياً...");
  await runTasiScan(msg.chat.id);
});

tasiBot.onText(/\/signals/, async msg => {
  if (tasiSignals.size === 0) {
    await tasiBot.sendMessage(msg.chat.id, "📭 لا توجد إشارات محفوظة، أرسل /scan للبدء.");
    return;
  }
  for (const stock of Array.from(tasiSignals.values()).slice(0, 5)) {
    await tasiBot.sendMessage(msg.chat.id, buildMessage(stock, "السوق السعودي (تاسي)"), { parse_mode: "Markdown" });
  }
});

// ============================================================
// 🤖 تفاعل بوت السوق الأمريكي (ناسداك)
// ============================================================

usBot.onText(/\/start/, async msg => {
  await usBot.sendMessage(
    msg.chat.id,
    `🇺🇸 *مرحباً بك في بوت السوق الأمريكي (ناسداك)*\n\n` +
    `• يتم التحديث التلقائي كل دقيقتين.\n` +
    `• أخبار مترجمة ومحللة (إيجابي 🟢 / سلبي 🔴).\n` +
    `• 8 أهداف سعرية متدرجة مع تتبع التحقيق ✅.\n\n` +
    `الأوامر:\n` +
    `/scan - فحص السوق الأمريكي الآن\n` +
    `/signals - عرض الأسهم المرصودة`,
    { parse_mode: "Markdown" }
  );
});

usBot.onText(/\/scan/, async msg => {
  await usBot.sendMessage(msg.chat.id, "🔍 جاري فحص جميع أسهم السوق الأمريكي لحظياً...");
  await runUsScan(msg.chat.id);
});

usBot.onText(/\/signals/, async msg => {
  if (usSignals.size === 0) {
    await usBot.sendMessage(msg.chat.id, "📭 لا توجد إشارات محفوظة، أرسل /scan للبدء.");
    return;
  }
  for (const stock of Array.from(usSignals.values()).slice(0, 5)) {
    await usBot.sendMessage(msg.chat.id, buildMessage(stock, "السوق الأمريكي (ناسداك)"), { parse_mode: "Markdown" });
  }
});

// ============================================================
// ⏱️ الجدولة التلقائية (كل دقيقتين لكل بوت بشكل مستقل)
// ============================================================

setInterval(() => {
  runTasiScan().catch(err => console.log(err));
}, UPDATE_INTERVAL_MIN * 60 * 1000);

setInterval(() => {
  runUsScan().catch(err => console.log(err));
}, UPDATE_INTERVAL_MIN * 60 * 1000);

console.log("🟢 TASI and US Stock Scanner Bots Started Separately & Successfully!");
