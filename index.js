import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 // 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });
con
co

// 🔑 API
const API_KEY = "d75o0l1r01qk56kdfon0d75o0l1r01qk56kdfong";

let chatId = null;

// 🧠 تخزين آخر سعر لكل سهم (لمتابعة الموجة)
let memory = {};

bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX (WAVE MODE)");
    run();
  }

  if (msg.text === "/scan") {
    bot.sendMessage(chatId, "🚀 تحليل الموجات...");
    run();
  }
});

// =======================
// 🧠 تحليل + موجات
// =======================
function analyze(symbol, price, prev) {
  if (!price || !prev || prev === 0) return null;

  let change = ((price - prev) / prev) * 100;

  let signal = "⚪ محايد";
  let smart = "";
  let type = "🐠 مضاربين";

  if (change > 3) {
    signal = "💰 دخول مؤسسات";
    smart = "🔥 Smart Money";
    type = "🦈 هوامير";
  } else if (change < -3) {
    signal = "🚨 تصريف";
    type = "🦈 هوامير";
  } else if (change > 1.5) {
    signal = "🧠 تجميع";
  }

  // 🧠 تحليل الموجة
  let wave = "⚪ غير واضح";

  if (!memory[symbol]) {
    wave = "🚀 بداية موجة";
  } else {
    let last = memory[symbol];

    if (price > last * 1.03) {
      wave = "🔥 استمرار موجة";
    } 
    else if (price < last * 0.97) {
      wave = "⚠️ قرب التصريف";
    } 
    else {
      wave = "⏳ تذبذب";
    }
  }

  memory[symbol] = price;

  function fix(n) {
    return Number(n).toFixed(price < 1 ? 6 : 2);
  }

  let tp = [
    fix(price * 1.02),
    fix(price * 1.04),
    fix(price * 1.06),
    fix(price * 1.08),
    fix(price * 1.10),
    fix(price * 1.12),
    fix(price * 1.15),
    fix(price * 1.18),
  ];

  let sl = fix(price * 0.95);

  return { signal, tp, sl, change, smart, type, wave };
}

// =======================
function format(s) {
  return `
${s.market}
${s.type}

${s.name}

💰 ${Number(s.price).toFixed(s.price < 1 ? 6 : 2)}
📊 ${s.signal} (${s.change.toFixed(2)}%)
${s.smart ? "🧠 " + s.smart : ""}

🌊 ${s.wave}

🎯 TP1: ${s.tp[0]}
🎯 TP2: ${s.tp[1]}
🎯 TP3: ${s.tp[2]}
🎯 TP4: ${s.tp[3]}
🎯 TP5: ${s.tp[4]}
🎯 TP6: ${s.tp[5]}
🎯 TP7: ${s.tp[6]}
🎯 TP8: ${s.tp[7]}

🛑 SL: ${s.sl}
━━━━━━━━━━━━`;
}

// =======================
async function getQuote(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();
    if (!data || !data.c || !data.pc) return null;
    return { price: data.c, prev: data.pc };
  } catch { return null; }
}

// =======================
let running = false;

async function run() {
  if (!chatId || running) return;
  running = true;

  try {

    let symbols = ["AAPL","TSLA","NVDA","META","AMD"];

    for (let sym of symbols) {
      let q = await getQuote(sym);
      if (!q) continue;

      let a = analyze(sym, q.price, q.prev);
      if (!a) continue;

      await bot.sendMessage(chatId, format({
        name:sym,
        market:"🇺🇸 السوق الأمريكي",
        price:q.price,
        ...a
      }));

      await new Promise(r => setTimeout(r, 300));
    }

  } catch (e) {
    console.log(e);
  }

  running = false;
}

setInterval(run, 60000);

app.listen(3000, () => {
  console.log("💀 WAVE MODE RUNNING");
});
