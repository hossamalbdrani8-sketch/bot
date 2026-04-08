import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";

// 💀 اتصال قوي ثابت
const bot = new TelegramBot(TOKEN, {
  polling: {
    interval: 300,
    autoStart: true,
    params: { timeout: 10 }
  }
});

// 🔑 API
const API_KEY = "d7a0311r01qspme6c44gd7a0311r01qspme6c450";

let chatId = null;
let memory = {};
let running = false;

// 💀 حماية
process.on("uncaughtException", (err) => {
  console.log("💀 CRASH:", err.message);
});

process.on("unhandledRejection", (err) => {
  console.log("💀 PROMISE ERROR:", err);
});

// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX ELITE MODE (ULTIMATE)");
    run();
  }

  if (msg.text === "/scan") {
    bot.sendMessage(chatId, "🚀 فحص السوق...");
    run();
  }
});

// =======================
function analyze(price, prev, symbol) {
  if (!price || !prev || prev === 0 || price <= 0) return null;

  let change = ((price - prev) / prev) * 100;

  let signal = "⚪ محايد";
  let emoji = "";
  let smart = "";
  let type = "🐠 مضاربين";
  let entry = "⏳ انتظر";
  let alert = "";

  if (!memory[symbol]) {
    memory[symbol] = {
      price,
      low: price,
      high: price,
      momentum: 0
    };
  }

  let prevData = memory[symbol];

  if (price < prevData.low) prevData.low = price;
  if (price > prevData.high) prevData.high = price;

  let fromLow = ((price - prevData.low) / prevData.low) * 100;
  let momentum = price - prevData.price;

  let flow = "⚠️ ضعف السيولة";
  if (momentum > 0 && change > 0.5) flow = "💹 سيولة مستمرة";
  if (momentum > 0.5 && change > 1.5) flow = "🔥💹 سيولة قوية";
  if (momentum > 1 && change > 2.5) flow = "💀🚀 سيولة انفجار";

  // 💀 تنبيه قبل الانفجار
  if (momentum > 0.4 && change > 1 && fromLow > 2) {
    alert = "⚠️💀 اقتراب انفجار";
  }

  // 💀 تأكيد انفجار
  if (momentum > 1 && change > 2.5 && fromLow > 3) {
    alert = "💀🚀 انفجار فعلي";
  }

  if (change > 4) {
    signal = "💀🚀 دخول مؤسسات ضخم";
    emoji = "🔥";
    smart = "💀 Smart Money ELITE";
    type = "🦈 هوامير";
  } 
  else if (change > 2) {
    signal = "🔥 تجميع قوي";
    smart = "📈 Accumulation PRO";
  } 
  else if (change < -4) {
    signal = "🚨 تصريف عنيف";
    emoji = "⚡️";
    smart = "📉 Distribution";
    type = "🦈 هوامير";
  }

  if (fromLow > 1.5 && change > 0.3 && momentum > 0) entry = "⚡️ دخول مبكر";
  if (fromLow > 2 && change > 1) entry = "💀 دخول ذكي";

  // 💀 دخول مؤكد
  if (fromLow > 3 && change > 2 && flow.includes("💹")) {
    entry = "💀🔥 دخول مؤكد";
  }

  // 💀 ELITE
  if (fromLow > 4 && change > 3 && flow.includes("💀")) {
    entry = "💀🚀 دخول ELITE مؤكد";
  }

  function fix(n) {
    return Number(n).toFixed(price < 1 ? 6 : 2);
  }

  let tpRaw = [
    price*1.02, price*1.04, price*1.06, price*1.08,
    price*1.10, price*1.12, price*1.15, price*1.18
  ];

  let tp = tpRaw.map(fix);
  let tpStatus = tpRaw.map(v => price >= v);
  let sl = fix(price * 0.95);

  memory[symbol] = {
    price,
    low: prevData.low,
    high: prevData.high,
    momentum
  };

  return { signal,tp,sl,emoji,change,smart,type,entry,flow,tpStatus,fromLow,alert };
}

// =======================
function format(s) {
  return `
${s.market}
${s.type}

${s.emoji} ${s.name}

💰 ${Number(s.price).toFixed(s.price < 1 ? 6 : 2)}
📉 من القاع: ${s.fromLow.toFixed(2)}%

📊 ${s.signal} (${s.change.toFixed(2)}%)
${s.smart ? "🧠 " + s.smart : ""}

🎯 TP1: ${s.tp[0]}
🎯 TP2: ${s.tp[1]}
🎯 TP3: ${s.tp[2]}
🎯 TP4: ${s.tp[3]}
🎯 TP5: ${s.tp[4]}
🎯 TP6: ${s.tp[5]}
🎯 TP7: ${s.tp[6]}
🎯 TP8: ${s.tp[7]}

🛑 SL: ${s.sl}

${s.entry}
${s.flow}
${s.alert ? "🚨 " + s.alert : ""}

━━━━━━━━━━━━`;
}

// باقي الكود بدون أي تغيير 🔥
