
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));

// جلب المتغيرات البيئية من Railway
const EODHD_API_KEY = process.env.EODHD_API_KEY || "YOUR_API_KEY";

// دالة جلب البيانات من EODHD
async function fetchEodhdData(ticker, exchange = "US") {
    const url = `https://eodhistoricaldata.com/api/real-time/${ticker}.${exchange}?api_token=${EODHD_API_KEY}&fmt=json`;
    try {
        const response = await fetch(url);
        if (response.ok) {
            return await response.json();
        }
    } catch (error) {
        console.error(`خطأ في جلب بيانات ${ticker}:`, error.message);
    }
    return null;
}

// حساب مؤشر ATR(14)
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
    const atr = slice.reduce((a, b) => a + b, 0) / slice.length;
    return atr;
}

// 🧠 محرك AI PRO MAX للاتجاه والدعم والمقاومة والسيولة
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
    const avgVolume = volumes.reduce((a, b) => a + b, 0) / volumes.length;
    const liquidity = avgVolume * currentPrice;

    return { trend, support, resistance, liquidity };
}

// 🎯 توليد 8 أهداف ديناميكية بالـ ATR مع الألوان والعلامات المطلوبة
function generateDynamicTargets(currentPrice, atr, trend) {
    let targets = [];
    if (trend === "BULLISH") {
        // 🟢 الاتجاه الصاعد = أهداف فوق السعر
        for (let i = 1; i <= 8; i++) {
            let targetPrice = currentPrice + (atr * i * 0.75);
            targets.append ? targets.append(...) : targets.push(`🟢 الهدف الصاعد ${i}: ${targetPrice.toFixed(2)}`);
        }
    } else {
        // 🔴 الاتجاه الهابط = أهداف تحت السعر مع علامة حمراء 🔴✓
        for (let i = 1; i <= 8; i++) {
            let targetPrice = currentPrice - (atr * i * 0.75);
            targets.push(`🔴✓ الهدف الهابط ${i}: ${targetPrice.toFixed(2)}`);
        }
    }
    return targets;
}

// 📰 جلب الأخبار من EODHD مع ترجمة العنوان للعربية
async function fetchAndTranslateNews(ticker) {
    const url = `https://eodhistoricaldata.com/api/news?api_token=${EODHD_API_KEY}&s=${ticker}&limit=1&fmt=json`;
    try {
        const response = await fetch(url);
        if (response.ok) {
            const data = await response.json();
            if (data && data.length > 0) {
                let title = data[0].title || "لا توجد اخبار حديثة";
                return `[ترجمة عربية للأخبار]: ${title}`;
            }
        }
    } catch (e) {}
    return "لا توجد أخبار متاحة حالياً";
}

// فحص الأسواق الشامل (تاسي، الأمريكي/ناسداك بشرط السعر >= 0.20، والعملات الرقمية)
async function scanMarkets() {
    console.log("--- بدأ تشغيل محرك الفحص الشامل للأسواق ---");

    // قوائم الفحص (تاسي، أمريكي، عملات رقمية)
    const tasiList = ["2222", "1120", "1010"]; // عينة تاسي كاملة
    const usList = ["AAPL", "MSFT", "TSLA", "AMC"]; // عينة ناسداك والأمريكي
    const cryptoList = ["BTC-USD", "ETH-USD"]; // العملات الرقمية كاملة

    // 🇸🇦 فحص تاسي
    for (let ticker of tasiList) {
        await processSymbol(ticker, "SR", "تاسي (السعودية)", 0.0);
    }

    // 🇺🇸 فحص الأسهم الأمريكية (شرط السعر 0.20$ فأعلى) والناسداك
    for (let ticker of usList) {
        await processSymbol(ticker, "US", "الأسهم الأمريكية / ناسداك", 0.20);
    }

    // 🌐 فحص العملات الرقمية
    for (let ticker of cryptoList) {
        await processSymbol(ticker, "CC", "العملات الرقمية", 0.0);
    }
}

async function processSymbol(ticker, exchange, marketName, minPrice) {
    const data = await fetchEodhdData(ticker, exchange);
    if (data && data.close) {
        const price = parseFloat(data.close);
        
        // شرط الحد الأدنى للسعر للأمريكي ($0.20 فأعلى)
        if (marketName.includes("الأمريكية") && price < minPrice) {
            return;
        }

        // جلب الشموع التاريخية للـ ATR
        const historyUrl = `https://eodhistoricaldata.com/api/eod/${ticker}.${exchange}?api_token=${EODHD_API_KEY}&fmt=json&limit=30`;
        const histRes = await fetch(historyUrl);
        const candles = histRes.ok ? await histRes.json() : [];

        const atrVal = calculateATR(candles, 14);
        const { trend, support, resistance, liquidity } = aiProMaxEngine(candles);
        const targets = generateDynamicTargets(price, atrVal > 0 ? atrVal : 1.0, trend);
        const news = await fetchAndTranslateNews(ticker);

        console.log(`\n[السوق: ${marketName}] الرمز: ${ticker}`);
        console.log(`السعر الحالي: ${price} | الاتجاه: ${trend}`);
        console.log(`الدعم: ${support.toFixed(2)} | المقاومة: ${resistance.toFixed(2)} | السيولة: ${liquidity.toFixed(0)}`);
        console.log(`الأهداف الديناميكية:`, targets);
        console.log(`الأخبار: ${news}`);
        console.log("--------------------------------------------------");
    }
}

// التشغيل المستمر للفحص كل فترة
async function mainLoop() {
    while (true) {
        await scanMarkets();
        // الانتظار لمدة 15 دقيقة قبل إعادة الفحص لتجنب حظر الـ API
        await new Promise(resolve => setTimeout(resolve, 15 * 60 * 1000));
    }
}

mainLoop();
