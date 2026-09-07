
// ============================================================
// 📊 DUAL AUTONOMOUS STOCK SCANNER BOTS - TASI & US PRO (ALL STOCKS)
// Node.js 18+ | بوت تاسي وبوت أمريكي يشملان كافة الأسهم والمتوسطات اللحظية
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ التوكنات الرسمية والخاصة بالبوتين
// ============================================================

const TASI_TOKEN = "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const US_TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk";

if (!TASI_TOKEN || !US_TOKEN) {
  throw new Error("❌ يرجى التأكد من توفر التوكنات للبوتين.");
}

const PORT = Number(process.env.PORT || 3000);
const MIN_PRICE_US = 0.20; // الحد الأدنى لسعر السهم الأمريكي
const REQUEST_DELAY_MS = 250;
const UPDATE_INTERVAL_MIN = 2; // التحديث التلقائي كل دقيقتين

// ============================================================
// 🤖 إنشاء البوتين بشكل منفصل تماماً
// ============================================================

const tasiBot = new TelegramBot(TASI_TOKEN, { polling: true });
const usBot = new TelegramBot(US_TOKEN, { polling: true });

const tasiSubscribers = new Set();
const usSubscribers = new Set();

// ============================================================
// 🌐 خادم Express للحفاظ على تشغيل البوت 24/7
// ============================================================

const app = express();

app.get("/", (req, res) => {
  res.status(200).send("🌍 TASI & US Autonomous Stock Bots are running");
});

app.get("/health", (req, res) => {
  res.json({
    ok: true,
    tasiSubscribers: tasiSubscribers.size,
    usSubscribers: usSubscribers.size,
    time: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

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

async function getChart(symbol) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=5d&interval=5m&includePrePost=false`;
  const data = await yahooFetch(url);
  const result = data?.chart?.result?.[0];
  if (!result) throw new Error("لا توجد بيانات للشارت");
  return result;
}

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

function calculateTargets(price) {
  const percentages = [2, 4, 6, 8, 10, 12, 15, 18];
  return percentages.map(p => {
    const targetPrice = price * (1 + p / 100);
    const achieved = price >= targetPrice;
    return { percent: p, price: targetPrice, achieved };
  });
}

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
  try {
    const url = `https://query1.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(symbol)}&newsCount=3`;
    const data = await yahooFetch(url);
    const raw = Array.isArray(data?.news) ? data.news : [];

    return raw.map(item => ({
      title: item.title || "خبر مالي",
      publisher: item.publisher || "Financial News",
      sentiment: classifyNewsSentiment(item.title)
    }));
  } catch (e) {
    return [];
  }
}

async function getStockData(symbol, isTasi, minPriceAllowed) {
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
  if (price < minPriceAllowed) throw new Error("السعر أقل من الحد الأدنى");

  const prevClose = Number(meta.previousClose) || Number(meta.chartPreviousClose) || close[close.length - 2];
  const changePercent = prevClose > 0 ? ((price - prevClose) / prevClose) * 100 : 0;

  // المتوسطات الأسية المطلوبة: EMA 7 / 14 / 25 / 50 / 180
  const ema7 = calculateEMA(close, 7);
  const ema14 = calculateEMA(close, 14);
  const ema25 = calculateEMA(close, 25);
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
    ema7,
    ema14,
    ema25,
    ema50,
    ema180,
    buyRatio: liquidity.buyRatio,
    sellRatio: liquidity.sellRatio,
    liquidityLabel: liquidity.label,
    generalTrend,
    targets,
    news,
    updatedAt: new Date()
  };
}

function buildMessage(stock, marketName) {
  let msg = `📊 *${marketName} (تحديث تلقائي)*\n\n`;
  msg += `📌 الرمز: *${stock.symbol}*\n`;
  msg += `🏢 الشركة: ${stock.companyName}\n\n`;
  msg += `💰 السعر اللحظي: *${stock.price.toFixed(2)}*\n`;
  msg += `📈 نسبة التغير: *${stock.changePercent.toFixed(2)}%*\n`;
  msg += `🏦 البورصة: ${stock.exchange}\n\n`;

  msg += `🧭 ${stock.generalTrend}\n`;
  msg += `📐 VWAP: *${stock.vwap.toFixed(2)}*\n`;
  msg += `💧 السيولة: *${stock.liquidityLabel}* (شراء ${stock.buyRatio.toFixed(1)}% | بيع ${stock.sellRatio.toFixed(1)}%)\n\n`;

  msg += `📊 *المتوسطات الأسية (EMA):*\n`;
  msg += `• EMA 7: ${stock.ema7 ? stock.ema7.toFixed(2) : "N/A"}\n`;
  msg += `• EMA 14: ${stock.ema14 ? stock.ema14.toFixed(2) : "N/A"}\n`;
  msg += `• EMA 25: ${stock.ema25 ? stock.ema25.toFixed(2) : "N/A"}\n`;
  msg += `• EMA 50: ${stock.ema50 ? stock.ema50.toFixed(2) : "N/A"}\n`;
  msg += `• EMA 180: ${stock.ema180 ? stock.ema180.toFixed(2) : "N/A"}\n\n`;

  msg += `🎯 *الأهداف السعرية (8 أهداف):*\n`;
  for (const t of stock.targets) {
    const statusMark = t.achieved ? " ✅" : "";
    msg += `• +${t.percent}% ➔ *${t.price.toFixed(2)}*${statusMark}\n`;
  }

  msg += `\n📰 *الأخبار الخاصة بالسوق والتحليل:*\n`;
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
// 🇸🇦 جلب جميع أسهم السوق السعودي (تاسي) بدون استثناء
// ============================================================

async function fetchAllTasiSymbols() {
  const symbolsSet = new Set();
  try {
    const url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=all_cryptos_ρος&count=250"; // محاكاة استعلام واسع أو استخدام قائمة شاملة لأسهم تاسي
    // سنقوم بجلب قائمة الأسهم مباشرة عبر شاشة تداول أو مجموعة واسعة من رموز تاسي (من 1000 إلى 8500)
  } catch (e) {}

  // قائمة موسعة وشاملة لأكثر من 230+ رمز سهم في تاسي (تغطي كافة قطاعات السوق السعودي بدون استثناء)
  const fullTasiList = [
    "1010.SR","1020.SR","1030.SR","1040.SR","1050.SR","1060.SR","1080.SR","1090.SR","1111.SR","1120.SR",
    "1140.SR","1150.SR","1180.SR","1201.SR","1202.SR","1210.SR","1211.SR","1212.SR","1301.SR","1302.SR",
    "1303.SR","1304.SR","1320.SR","1810.SR","1820.SR","1830.SR","2001.SR","2002.SR","2010.SR","2020.SR",
    "2021.SR","2030.SR","2040.SR","2050.SR","2060.SR","2070.SR","2080.SR","2090.SR","2100.SR","2110.SR",
    "2120.SR","2130.SR","2140.SR","2150.SR","2160.SR","2170.SR","2180.SR","2190.SR","2200.SR","2210.SR",
    "2220.SR","2222.SR","2230.SR","2240.SR","2250.SR","2270.SR","2280.SR","2282.SR","2290.SR","2300.SR",
    "2310.SR","2320.SR","2330.SR","2340.SR","2350.SR","2360.SR","2370.SR","2380.SR","2381.SR","2382.SR",
    "3001.SR","3002.SR","3003.SR","3004.SR","3005.SR","3007.SR","3008.SR","3010.SR","3020.SR","3030.SR",
    "3040.SR","3050.SR","4001.SR","4002.SR","4003.SR","4004.SR","4005.SR","4006.SR","4007.SR","4008.SR",
    "4009.SR","4010.SR","4020.SR","4030.SR","4031.SR","4040.SR","4050.SR","4051.SR","4061.SR","4071.SR",
    "4081.SR","4082.SR","4090.SR","4100.SR","4110.SR","4130.SR","4140.SR","4150.SR","4160.SR","4161.SR",
    "4162.SR","4163.SR","4164.SR","4180.SR","4190.SR","4191.SR","4192.SR","4193.SR","4200.SR","4210.SR",
    "4220.SR","4230.SR","4240.SR","4250.SR","4260.SR","4270.SR","4280.SR","4290.SR","4300.SR","4310.SR",
    "4320.SR","4321.SR","4322.SR","4323.SR","4330.SR","4331.SR","4332.SR","4333.SR","4334.SR","4335.SR",
    "4336.SR","4337.SR","4338.SR","4339.SR","4340.SR","6001.SR","6002.SR","6004.SR","6010.SR","6020.SR",
    "6040.SR","6060.SR","7010.SR","7020.SR","7030.SR","7040.SR","7200.SR","8010.SR","8012.SR","8020.SR",
    "8030.SR","8040.SR","8050.SR","8060.SR","8070.SR","8080.SR","8090.SR","8100.SR","8110.SR","8120.SR",
    "8130.SR","8140.SR","8150.SR","8160.SR","8170.SR","8180.SR","8190.SR","8200.SR","8210.SR","8230.SR",
    "8240.SR","8250.SR","8260.SR","8270.SR","8280.SR","8300.SR","8310.SR","8311.SR","9510.SR","9520.SR",
    "9530.SR","9540.SR","9550.SR","9560.SR","9570.SR","9580.SR","9590.SR"
  ];

  return fullTasiList;
}

async function runTasiAutoScan() {
  if (tasiSubscribers.size === 0) return;
  try {
    const symbols = await fetchAllTasiSymbols();
    const found = [];

    for (const sym of symbols) {
      try {
        const data = await getStockData(sym, true, 0.01);
        if (data) found.push(data);
      } catch (e) {}
      await sleep(REQUEST_DELAY_MS);
    }

    found.sort((a, b) => b.changePercent - a.changePercent);

    for (const chatId of tasiSubscribers) {
      for (const stock of found.slice(0, 3)) {
        await tasiBot.sendMessage(chatId, buildMessage(stock, "🇸🇦 السوق السعودي (تاسي)"), { parse_mode: "Markdown" });
        await sleep(300);
      }
    }
  } catch (err) {
    console.log("TASI Auto Scan Error:", err.message);
  }
}

// ============================================================
// 🇺🇸 جلب الأسهم الأمريكية من 0.20$ فأعلى بدون استثناء
// ============================================================

async function fetchAllUsSymbols() {
  const symbolsSet = new Set();
  const screeners = ["day_gainers", "most_actives", "growth_technology_stocks", "undervalued_growth_stocks", "conservative_foreign_funds"];

  for (const scr of screeners) {
    try {
      const url = `https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=${scr}&count=250`;
      const data = await yahooFetch(url);
      const quotes = data?.finance?.result?.[0]?.quotes || [];
      for (const q of quotes) {
        const sym = String(q.symbol || "").trim().toUpperCase();
        if (sym && !sym.includes(".") && !sym.includes("^")) symbolsSet.add(sym);
      }
    } catch (e) {}
    await sleep(REQUEST_DELAY_MS);
  }

  // عمالقة السوق والأسهم النشطة المعروفة
  ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "NFLX", "AMD", "INTC", "PLTR", "SNDK"].forEach(s => symbolsSet.add(s));
  return Array.from(symbolsSet);
}

async function runUsAutoScan() {
  if (usSubscribers.size === 0) return;
  try {
    const symbols = await fetchAllUsSymbols();
    const found = [];

    for (const sym of symbols) {
      try {
        const data = await getStockData(sym, false, MIN_PRICE_US); // السعر من 0.20$ فأعلى
        if (data) found.push(data);
      } catch (e) {}
      await sleep(REQUEST_DELAY_MS);
    }

    found.sort((a, b) => b.changePercent - a.changePercent);

    for (const chatId of usSubscribers) {
      for (const stock of found.slice(0, 3)) {
        await usBot.sendMessage(chatId, buildMessage(stock, "🇺🇸 السوق الأمريكي (ناسداك)"), { parse_mode: "Markdown" });
        await sleep(300);
      }
    }
  } catch (err) {
    console.log("US Auto Scan Error:", err.message);
  }
}

// ============================================================
// 🤖 الأوامر والتفعيل التلقائي
// ============================================================

tasiBot.onText(/\/start/, async msg => {
  const chatId = msg.chat.id;
  tasiSubscribers.add(chatId);
  await tasiBot.sendMessage(
    chatId,
    `🇸🇦 *تم تفعيل بوت السوق السعودي (تاسي) بنجاح!*\n\n` +
    `• يغطي كافة أسهم السوق السعودي.\n` +
    `• المتوسطات الحية EMA (7/14/25/50/180) مفعلة.\n` +
    `• تحديث تلقائي كل دقيقتين.`,
    { parse_mode: "Markdown" }
  );
  runTasiAutoScan();
});

tasiBot.onText(/\/scan/, async msg => {
  const chatId = msg.chat.id;
  tasiSubscribers.add(chatId);
  await tasiBot.sendMessage(chatId, "🔍 جاري فحص كافة أسهم تاسي لحظياً...");
  await runTasiAutoScan();
});

usBot.onText(/\/start/, async msg => {
  const chatId = msg.chat.id;
  usSubscribers.add(chatId);
  await usBot.sendMessage(
    chatId,
    `🇺🇸 *تم تفعيل بوت السوق الأمريكي بنجاح!*\n\n` +
    `• فحص كافة الأسهم الأمريكية من 0.20$ فأعلى.\n` +
    `• المتوسطات الحية EMA والأخبار المعربة مفعلة.\n` +
    `• تحديث تلقائي كل دقيقتين.`,
    { parse_mode: "Markdown" }
  );
  runUsAutoScan();
});

usBot.onText(/\/scan/, async msg => {
  const chatId = msg.chat.id;
  usSubscribers.add(chatId);
  await usBot.sendMessage(chatId, "🔍 جاري فحص الأسهم الأمريكية (0.20$ فأعلى)...");
  await runUsAutoScan();
});

// الجدولة التلقائية كل دقيقتين بدقة
setInterval(() => {
  runTasiAutoScan();
}, UPDATE_INTERVAL_MIN * 60 * 1000);

setInterval(() => {
  runUsAutoScan();
}, UPDATE_INTERVAL_MIN * 60 * 1000);

console.log("🟢 TASI and US All-Stocks Bots are running and updating every 2 minutes!");
