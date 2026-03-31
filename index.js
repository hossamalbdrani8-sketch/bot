import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 التوكن
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";

// ✅ بدون polling (Webhook mode)
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
// 📩 استقبال Telegram (Webhook)
// =======================
app.post("/webhook", async (req, res) => {
  const update = req.body;

  try {
    bot.processUpdate(update);

    if (update.message) {
      chatId = update.message.chat.id;
      const text = update.message.text;

      // /start
      if (text === "/start") {
        bot.sendMessage(chatId, "💀 AI PRO MAX CONNECTED");
      }

      // /scan
      if (text === "/scan") {
        bot.sendMessage(chatId, "🚀 AI PRO MAX SCANNING...");

        try {
          // 🇺🇸 أمريكا
          const us = await fetch("https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAPL,TSLA,NVDA,MSFT,AMZN,META")
            .then(r => r.json());

          // 🇸🇦 السعودية
          const sa = await fetch("https://query1.finance.yahoo.com/v7/finance/quote?symbols=2222.SR,1120.SR,2010.SR,7010.SR")
            .then(r => r.json());

          // 💱 العملات
          const fx = await fetch("https://query1.finance.yahoo.com/v7/finance/quote?symbols=EURUSD=X,GBPUSD=X,USDJPY=X,BTC-USD")
            .then(r => r.json());

          const process = (arr) => {
            return arr.map(s => analyze(
              s.symbol,
              s.regularMarketPrice,
              s.regularMarketChangePercent || 0
            )).join("\n");
          };

          let message = `💀 AI PRO MAX MARKET

🇺🇸 أمريكا:
${process(us.quoteResponse.result)}

🇸🇦 السعودية:
${process(sa.quoteResponse.result)}

💱 العملات:
${process(fx.quoteResponse.result)}
`;

          bot.sendMessage(chatId, message);

        } catch (e) {
          bot.sendMessage(chatId, "❌ فشل جلب السوق");
        }
      }
    }

    res.sendStatus(200);

  } catch (err) {
    res.sendStatus(500);
  }
});

// =======================
// 🔥 TradingView Webhook
// =======================
app.post("/signal", (req, res) => {
  const data = req.body;

  if (!chatId) return res.send("No chatId");

  let message = `🚨 AI PRO MAX SIGNAL

📊 ${data.symbol}
💰 ${data.price}
RSI: ${data.rsi}

${data.signal}

🎯 TP1: ${data.tp1}
🎯 TP2: ${data.tp2}
🎯 TP3: ${data.tp3}
🎯 TP4: ${data.tp4}
🎯 TP5: ${data.tp5}
🎯 TP6: ${data.tp6}
🎯 TP7: ${data.tp7}
🎯 TP8: ${data.tp8}
`;

  bot.sendMessage(chatId, message);

  res.send("OK");
});

// =======================
// 🌐 الصفحة الرئيسية
// =======================
app.get("/", (req, res) => {
  res.send("💀 AI PRO MAX RUNNING");
});

// =======================
const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log("🚀 Server running on " + PORT);
});
