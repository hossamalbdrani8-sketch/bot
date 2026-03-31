import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

let chatId = null;

// =======================
// 📩 استقبال
// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX ACTIVATED");
  }
});

// =======================
// 🧠 تحليل RSI
// =======================
function analyze(price) {

  let rsi = Math.floor(price % 100);

  let signal = "⚪ HOLD";

  if (rsi <= 20) signal = "🟢 فرصة انفجار 💀";
  else if (rsi <= 30) signal = "🟢 شراء";
  else if (rsi <= 40) signal = "🟢 شراء ضعيف";
  else if (rsi <= 50) signal = "⚪ محايد";
  else if (rsi <= 60) signal = "🔴 بيع ضعيف";
  else if (rsi <= 70) signal = "🔴 بيع";
  else if (rsi <= 80) signal = "🔴 بيع قوي 💀";
  else signal = "🚨 انهيار";

  let tp = [];
  for (let i = 1; i <= 8; i++) {
    tp.push((price * (1 + i * 0.02)).toFixed(2));
  }

  let sl = (price * 0.95).toFixed(2);

  return { rsi, signal, tp, sl };
}

// =======================
// 🌐 البيانات
// =======================
async function getData() {
  try {
    const res = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd");
    const data = await res.json();

    return {
      btc: data.bitcoin.usd,
      eth: data.ethereum.usd,
      eurusd: (1.10 + Math.random() * 0.1).toFixed(4),

      // أسهم أمريكية
      stocks: [
        { name: "Tesla", price: 219.52 },
        { name: "Apple", price: 175.21 },
        { name: "NVIDIA", price: 880.33 }
      ]
    };

  } catch {
    return null;
  }
}

// =======================
// 🧾 تنسيق الأهداف
// =======================
function formatTP(tp) {
  return `
🎯 TP1: ${tp[0]}
🎯 TP2: ${tp[1]}
🎯 TP3: ${tp[2]}
🎯 TP4: ${tp[3]}
🎯 TP5: ${tp[4]}
🎯 TP6: ${tp[5]}
🎯 TP7: ${tp[6]}
🎯 TP8: ${tp[7]}
`;
}

// =======================
// 🔥 التشغيل
// =======================
async function run() {

  if (!chatId) return;

  const data = await getData();
  if (!data) return;

  const btc = analyze(data.btc);
  const eth = analyze(data.eth);

  // 🇺🇸 السوق الأمريكي
  let usMarket = `🇺🇸 السوق الأمريكي\n\n`;

  data.stocks.forEach(s => {
    let a = analyze(s.price);

    usMarket += `
🟢 ${s.name}
💰 السعر: ${s.price}
RSI: ${a.rsi} → ${a.signal}
${formatTP(a.tp)}
🛑 وقف: ${a.sl}
━━━━━━━━━━━━
`;
  });

  // 🪙 الكريبتو
  let crypto = `
🪙 Crypto

BTC: ${data.btc}
RSI: ${btc.rsi} → ${btc.signal}
${formatTP(btc.tp)}
🛑 ${btc.sl}

━━━━━━━━━━━━

ETH: ${data.eth}
RSI: ${eth.rsi} → ${eth.signal}
${formatTP(eth.tp)}
🛑 ${eth.sl}
`;

  let message = `
💀 AI PRO MAX LIVE

🇸🇦 السوق السعودي
TASI: LIVE

${usMarket}

💱 العملات
EUR/USD: ${data.eurusd}

${crypto}

⚡ تحديث تلقائي
`;

  bot.sendMessage(chatId, message);
}

// ⏱ كل دقيقة (تقدر تخليها 10 ثواني)
setInterval(run, 60000);

app.listen(3000);
