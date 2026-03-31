import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 التوكن
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN);

// 🎯 chatId
let chatId = null;

// =======================
// 📊 تحليل ذكي
// =======================
function analyze(symbol, price, change) {
  let signal = "⚪ HOLD";

  if (change > 1.5) signal = "🟢 BUY";
  if (change < -1.5) signal = "🔴 SELL";

  return `📊 ${symbol}
💰 ${price}
📈 ${change.toFixed(2)}%

💀 SIGNAL: ${signal}
🎯 TP: ${(price * 1.02).toFixed(2)}
🛑 SL: ${(price * 0.98).toFixed(2)}
`;
}

// =======================
// 🚀 AUTO SCAN
// =======================
async function autoScan() {
  if (!chatId) return;

  try {
    const us = await (await fetch("https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAPL,TSLA,NVDA,MSFT")).json();
    const sa = await (await fetch("https://query1.finance.yahoo.com/v7/finance/quote?symbols=2222.SR,1120.SR")).json();
    const fx = await (await fetch("https://query1.finance.yahoo.com/v7/finance/quote?symbols=EURUSD=X,BTC-USD")).json();

    const process = (arr) =>
      arr.map(s =>
        analyze(
          s.symbol,
          s.regularMarketPrice,
          s.regularMarketChangePercent || 0
        )
      ).join("\n");

    let message = `💀 AUTO AI MARKET

🇺🇸 أمريكا:
${process(us.quoteResponse.result)}

🇸🇦 السعودية:
${process(sa.quoteResponse.result)}

💱 العملات:
${process(fx.quoteResponse.result)}
`;

    bot.sendMessage(chatId, message);

  } catch (e) {
    console.log("❌ Error fetching market");
  }
}

// =======================
// ⏱ تشغيل كل دقيقة
// =======================
setInterval(autoScan, 60000);

// =======================
// 📩 Webhook
// =======================
app.post("/webhook", (req, res) => {
  const update = req.body;

  bot.processUpdate(update);

  if (update.message) {
    chatId = update.message.chat.id;

    if (update.message.text === "/start") {
      bot.sendMessage(chatId, "💀 AUTO AI PRO MAX ACTIVATED");
    }
  }

  res.sendStatus(200);
});

// =======================
app.get("/", (req, res) => {
  res.send("💀 RUNNING");
});

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log("🚀 Server running on " + PORT);
});
