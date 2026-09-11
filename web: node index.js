
const EODHD_API_KEY = process.env.EODHD_API_KEY || "YOUR_API_KEY";

async function fetchEodhdData(ticker, exchange = "US") {
    const url = `https://eodhistoricaldata.com/api/real-time/${ticker}.${exchange}?api_token=${EODHD_API_KEY}&fmt=json`;
    try {
        const response = await fetch(url);
        if (response.ok) {
            return await response.json();
        }
    } catch (error) {
        console.error(`خطأ في جلب بيانات ${ticker}`);
    }
    return null;
}

function calculateATR(candles, period = 14) {
    if (!candles || candles.length < period) return 1.0;
    let trList = [];
    for (let i = 1; i < candles.length; i++) {
        const high = parseFloat(candles[i].high || 0);
        const low = parseFloat(candles[i].low || 0);
        const closePrev = parseFloat(candles[i - 1].close || 0);
        const tr = Math.max(high - low, Math.abs(high - closePrev), Math.abs(low - closePrev));
        trList.push(tr);
    }
    const slice = trList.slice(-period);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
}

function aiProMaxEngine(candles) {
    if (!candles || candles.length < 20) return { trend: "NEUTRAL", support: 0, resistance: 0, liquidity: 0 };
    const closes = candles.map(c => parseFloat(c.close || 0));
    const highs = candles.map(c => parseFloat(c.high || 0));
    const lows = candles.map(c => parseFloat(c.low || 0));
    
    const currentPrice = closes[closes.length - 1];
    const sma20 = closes.slice(-20).reduce((a, b) => a + b, 0) / 20;
    
    const trend = currentPrice >= sma20 ? "BULLISH" : "BEARISH";
    const support = Math.min(...lows.slice(-20));
    const resistance = Math.max(...highs.slice(-20));
    const volumes = candles.slice(-5).map(c => parseFloat(c.volume || 0));
    const liquidity = (volumes.reduce((a, b) => a + b, 0) / volumes.length) * currentPrice;

    return { trend, support, resistance, liquidity };
}

function generateDynamicTargets(currentPrice, atr, trend) {
    let targets = [];
    if (trend === "BULLISH") {
        for (let i = 1; i <= 8; i++) {
            targets.push(`🟢 الهدف الصاعد ${i}: ${(currentPrice + (atr * i * 0.75)).toFixed(2)}`);
        }
    } else {
        for (let i = 1; i <= 8; i++) {
            targets.push(`🔴✓ الهدف الهابط ${i}: ${(currentPrice - (atr * i * 0.75)).toFixed(2)}`);
        }
    }
    return targets;
}

async function scanMarkets() {
    console.log("--- بدأ تشغيل محرك الفحص الشامل للأسواق ---");
    const tasiList = ["2222.SR", "1120.SR"];
    const usList = ["AAPL", "MSFT"];
    const cryptoList = ["BTC-USD.CC"];

    for (let ticker of tasiList) {
        await processSymbol(ticker, "تاسي", 0.0);
    }
    for (let ticker of usList) {
        await processSymbol(ticker, "الامريكي", 0.20);
    }
    for (let ticker of cryptoList) {
        await processSymbol(ticker, "العملات الرقمية", 0.0);
    }
}

async function processSymbol(fullTicker, marketName, minPrice) {
    const parts = fullTicker.split('.');
    const ticker = parts[0];
    const exchange = parts[1] || "US";

    const data = await fetchEodhdData(ticker, exchange);
    if (data && data.close) {
        const price = parseFloat(data.close);
        if (marketName === "الامريكي" && price < minPrice) return;

        console.log(`\n[السوق: ${marketName}] الرمز: ${fullTicker} | السعر: ${price}`);
        console.log(`الأهداف والدعم والمقاومة جاهزة للتحليل.`);
    }
}

// تشغيل الفحص فوراً وتكراره
scanMarkets();
setInterval(scanMarkets, 15 * 60 * 1000);
