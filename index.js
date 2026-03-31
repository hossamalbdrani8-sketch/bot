import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN);

let chatId = null;

// =======================
// 📩 استقبال المستخدم
// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX ACTIVATED");
  }
});

// =======================
// 🧠 RSI ENGINE
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
// 🌐 جلب البيانات
// =======================
async function getData() {
  try {
    const res = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd");
    const data = await res.json();

    return {
      btc: data.bitcoin.usd,
      eth: data.ethereum.usd,
      eurusd: (1.10 + Math.random() * 0.1).toFixed(4),

      // محاكاة الأسواق
      tasi: "مفتوح",
      nasdaq: "مفتوح",

      // أسهم أمريكية (محاكاة قوية)
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
// 🔥 البث المباشر
// =======================
async function run() {

  if (!chatId) return;

  const data = await getData();
  if (!data) return;

  const btc = analyze(data.btc);
  const eth = analyze(data.eth);

  // 📊 تحليل الأسهم
  let stocksMsg = "";
  data.stocks.forEach(s => {
    let a = analyze(s.price);

    stocksMsg += `
🟢 ${s.name}
💰 السعر: ${s.price}
RSI: ${a.rsi}
${a.signal}

🎯 TP1: ${a.tp[0]}
🎯 TP2: ${a.tp[1]}
🎯 TP3: ${a.tp[2]}
🎯 TP4: ${a.tp[3]}
🎯 TP5: ${a.tp[4]}
🎯 TP6: ${a.tp[5]}
🎯 TP7: ${a.tp[6]}
🎯 TP8: ${a.tp[7]}

🛑 وقف: ${a.sl}
━━━━━━━━━━━━
`;
  });

  let message = `
💀 AI PRO MAX LIVE

🇸🇦 السوق السعودي
TASI: ${data.tasi}

🇺🇸 السوق الأمريكي
NASDAQ: ${data.nasdaq}

${stocksMsg}

💱 العملات
EUR/USD: ${data.eurusd}

🪙 Crypto

BTC: ${data.btc}
RSI: ${btc.rsi} → ${btc.signal}
🎯 ${btc.tp.join(" | ")}
🛑 ${btc.sl}

ETH: ${data.eth}
RSI: ${eth.rsi} → ${eth.signal}
🎯 ${eth.tp.join(" | ")}
🛑 ${eth.sl}

⚡ تحديث تلقائي
`;

  bot.sendMessage(chatId, message);
}

// ⏱ كل 60 ثانية (تقدر تخليها 10 ثواني)
setInterval(run, 60000);

// =======================
app.get("/", (req, res) => {
  res.send("AI PRO MAX RUNNING 💀");
});

app.listen(3000);
