 // ============================================================
// 🇺🇸 US STOCK TELEGRAM BOT PRO MAX
// EMA + LIQUIDITY + VOLUME + VWAP
// + PRICE >= $0.10
// + NYSE / NASDAQ / AMEX ONLY
// + MARKET CAP
// + STOCK MOVEMENT
// + ACCUMULATION / DISTRIBUTION
// + 4H LOW
// + GENERAL TREND
// + REVERSE SPLIT TODAY / MONTH / YEAR
// + DIVIDEND DATA
// + STRONG EXPLOSION FILTER
// Node.js 18+
// ============================================================

import express from "express";
import TelegramBot from "node-telegram-bot-api";

// ============================================================
// الإعدادات
// ============================================================

const TOKEN = process.env.TELEGRAM_TOKEN;

const PORT = Number(
  process.env.PORT || 3000
);

const MAX_SYMBOLS = Number(
  process.env.MAX_SYMBOLS || 250
);

const MIN_CHANGE = Number(
  process.env.MIN_CHANGE || 0.30
);

const MIN_PRICE = Number(
  process.env.MIN_PRICE || 0.10
);

const SCAN_INTERVAL_MIN = Number(
  process.env.SCAN_INTERVAL_MIN || 5
);

const UPDATE_INTERVAL_SEC = Number(
  process.env.UPDATE_INTERVAL_SEC || 30
);

const REQUEST_DELAY_MS = Number(
  process.env.REQUEST_DELAY_MS || 350
);

const SPLIT_CACHE_MS = Number(
  process.env.SPLIT_CACHE_MS || 60 * 1000
);

const DIVIDEND_CACHE_MS = Number(
  process.env.DIVIDEND_CACHE_MS || 5 * 60 * 1000
);

// ============================================================
// تحقق من التوكن
// ============================================================

if (!TOKEN) {

  console.error(
    "❌ TELEGRAM_TOKEN غير موجود"
  );

  process.exit(1);
}

// ============================================================
// Telegram
// ============================================================

const bot = new TelegramBot(
  TOKEN,
  {
    polling: true
  }
);

const app = express();

app.use(
  express.json()
);

// ============================================================
// التخزين
// ============================================================

const sentSignals =
  new Map();

const splitCache =
  new Map();

const dividendCache =
  new Map();

let scanning =
  false;

let lastScanTime =
  null;

let lastScanCount =
  0;

let cachedSymbols =
  [];

let symbolsCacheTime =
  0;

// ============================================================
// أدوات عامة
// ============================================================

function sleep(ms) {

  return new Promise(
    resolve =>
      setTimeout(resolve, ms)
  );
}

function roundPrice(price) {

  if (
    !Number.isFinite(price)
  ) {

    return "0.00";
  }

  return price.toFixed(2);
}

function formatNumber(value) {

  if (
    !Number.isFinite(value) ||
    value <= 0
  ) {

    return "—";
  }

  if (
    value >= 1_000_000_000
  ) {

    return (
      (value / 1_000_000_000)
        .toFixed(2) +
      "B"
    );
  }

  if (
    value >= 1_000_000
  ) {

    return (
      (value / 1_000_000)
        .toFixed(2) +
      "M"
    );
  }

  if (
    value >= 1_000
  ) {

    return (
      (value / 1_000)
        .toFixed(2) +
      "K"
    );
  }

  return Math.round(
    value
  ).toLocaleString(
    "en-US"
  );
}

function clamp(
  value,
  min,
  max
) {

  return Math.max(
    min,
    Math.min(max, value)
  );
}

// ============================================================
// التاريخ
// ============================================================

function startOfToday() {

  const d =
    new Date();

  d.setHours(
    0,
    0,
    0,
    0
  );

  return d;
}

function startOfMonth() {

  const d =
    new Date();

  d.setDate(1);

  d.setHours(
    0,
    0,
    0,
    0
  );

  return d;
}

function startOfYear() {

  const d =
    new Date();

  d.setMonth(
    0,
    1
  );

  d.setHours(
    0,
    0,
    0,
    0
  );

  return d;
}

// ============================================================
// Yahoo Finance
// ============================================================

async function yahooFetch(url) {

  const response =
    await fetch(
      url,
      {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",

          "Accept":
            "application/json"
        }
      }
    );

  if (!response.ok) {

    throw new Error(
      `Yahoo HTTP ${response.status}`
    );
  }

  return response.json();
}

// ============================================================
// الأسواق الأمريكية المسموح بها
// ============================================================

function isAllowedUSExchange(
  item
) {

  const exchange =
    String(
      item?.exchange ||
      ""
    ).toUpperCase();

  const fullExchange =
    String(
      item?.fullExchangeName ||
      ""
    ).toUpperCase();

  const allowedCodes = [
    "NMS",
    "NGM",
    "NCM",
    "NYQ",
    "ASE"
  ];

  if (
    allowedCodes.includes(
      exchange
    )
  ) {

    return true;
  }

  if (
    fullExchange.includes(
      "NASDAQ"
    )
  ) {

    return true;
  }

  if (
    fullExchange.includes(
      "NYSE"
    )
  ) {

    return true;
  }

  if (
    fullExchange.includes(
      "AMERICAN STOCK EXCHANGE"
    )
  ) {

    return true;
  }

  if (
    fullExchange.includes(
      "NYSE AMERICAN"
    )
  ) {

    return true;
  }

  return false;
}

// ============================================================
// تحليل Reverse Split
// ============================================================

function parseSplitRatio(
  ratio
) {

  if (!ratio) {

    return null;
  }

  const text =
    String(ratio)
      .trim()
      .replace(/\s/g, "");

  const match =
    text.match(
      /^([\d.]+):([\d.]+)$/
    );

  if (!match) {

    return null;
  }

  const first =
    Number(match[1]);

  const second =
    Number(match[2]);

  if (
    !Number.isFinite(first) ||
    !Number.isFinite(second) ||
    first <= 0 ||
    second <= 0
  ) {

    return null;
  }

  return {

    first,

    second,

    text:
      `${first} : ${second}`,

    reverse:
      first < second
  };
}

// ============================================================
// Reverse Split
// ============================================================

async function getReverseSplitInfo(
  symbol
) {

  const now =
    Date.now();

  const cached =
    splitCache.get(
      symbol
    );

  if (
    cached &&
    now - cached.time <
      SPLIT_CACHE_MS
  ) {

    return cached.data;
  }

  try {

    const url =
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}` +
      `?range=1y&interval=1d&events=split`;

    const data =
      await yahooFetch(
        url
      );

    const result =
      data?.chart?.result?.[0];

    if (!result) {

      const empty = {
        found: false
      };

      splitCache.set(
        symbol,
        {
          time: now,
          data: empty
        }
      );

      return empty;
    }

    const splits =
      result?.events?.splits ||
      {};

    const today =
      startOfToday().getTime();

    const month =
      startOfMonth().getTime();

    const year =
      startOfYear().getTime();

    let todaySplit =
      null;

    let monthSplit =
      null;

    let yearSplit =
      null;

    let latest =
      null;

    for (
      const key of
        Object.keys(splits)
    ) {

      const item =
        splits[key];

      const timestamp =
        Number(
          item?.date
        );

      if (
        !Number.isFinite(
          timestamp
        )
      ) {

        continue;
      }

      const parsed =
        parseSplitRatio(
          item?.splitRatio
        );

      if (
        !parsed ||
        !parsed.reverse
      ) {

        continue;
      }

      const date =
        new Date(
          timestamp * 1000
        );

      const info = {

        timestamp,

        date,

        ratio:
          parsed.text,

        first:
          parsed.first,

        second:
          parsed.second
      };

      if (
        !latest ||
        timestamp >
          latest.timestamp
      ) {

        latest =
          info;
      }

      const time =
        date.getTime();

      if (
        time >= today &&
        (
          !todaySplit ||
          timestamp >
            todaySplit.timestamp
        )
      ) {

        todaySplit =
          info;
      }

      if (
        time >= month &&
        (
          !monthSplit ||
          timestamp >
            monthSplit.timestamp
        )
      ) {

        monthSplit =
          info;
      }

      if (
        time >= year &&
        (
          !yearSplit ||
          timestamp >
            yearSplit.timestamp
        )
      ) {

        yearSplit =
          info;
      }
    }

    let selected =
      null;

    let period =
      null;

    if (todaySplit) {

      selected =
        todaySplit;

      period =
        "🔴 اليوم";

    } else if (
      monthSplit
    ) {

      selected =
        monthSplit;

      period =
        "🟠 هذا الشهر";

    } else if (
      yearSplit
    ) {

      selected =
        yearSplit;

      period =
        "🟡 هذه السنة";
    }

    const resultData = {

      found:
        Boolean(selected),

      period,

      ratio:
        selected?.ratio ||
        null,

      date:
        selected?.date ||
        null,

      timestamp:
        selected?.timestamp ||
        null,

      today:
        todaySplit,

      month:
        monthSplit,

      year:
        yearSplit,

      latest
    };

    splitCache.set(
      symbol,
      {
        time: now,
        data: resultData
      }
    );

    return resultData;

  } catch (error) {

    console.log(
      `⚠️ Reverse Split ${symbol}:`,
      error.message
    );

    return {
      found: false
    };
  }
}

// ============================================================
// تنسيق Reverse Split
// ============================================================

function formatReverseSplit(
  split
) {

  if (
    !split ||
    !split.found
  ) {

    return "";
  }

  const dateText =
    split.date
      ? split.date.toLocaleDateString(
          "ar-SA"
        )
      : "—";

  return `
🔄 تقسيم عكسي
${split.period}
🔢 النسبة: ${split.ratio}
📅 التاريخ: ${dateText}
`.trim();
}

// ============================================================
// بيانات التوزيعات
// ============================================================

async function getDividendInfo(
  symbol
) {

  const now =
    Date.now();

  const cached =
    dividendCache.get(
      symbol
    );

  if (
    cached &&
    now - cached.time <
      DIVIDEND_CACHE_MS
  ) {

    return cached.data;
  }

  try {

    const url =
      `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}` +
      `?range=1y&interval=1d&events=div`;

    const data =
      await yahooFetch(
        url
      );

    const result =
      data?.chart?.result?.[0];

    const dividends =
      result?.events?.dividends ||
      {};

    let latest =
      null;

    for (
      const key of
        Object.keys(dividends)
    ) {

      const item =
        dividends[key];

      const timestamp =
        Number(
          item?.date
        );

      const amount =
        Number(
          item?.amount
        );

      if (
        !Number.isFinite(timestamp) ||
        !Number.isFinite(amount)
      ) {

        continue;
      }

      if (
        !latest ||
        timestamp >
          latest.timestamp
      ) {

        latest = {

          timestamp,

          date:
            new Date(
              timestamp * 1000
            ),

          amount
        };
      }
    }

    const resultData = {

      found:
        Boolean(latest),

      latest
    };

    dividendCache.set(
      symbol,
      {
        time: now,
        data: resultData
      }
    );

    return resultData;

  } catch (error) {

    console.log(
      `⚠️ Dividend ${symbol}:`,
      error.message
    );

    return {
      found: false
    };
  }
}

// ============================================================
// تنسيق التوزيع
// ============================================================

function formatDividend(
  dividend
) {

  if (
    !dividend ||
    !dividend.found ||
    !dividend.latest
  ) {

    return "";
  }

  const item =
    dividend.latest;

  const dateText =
    item.date
      ? item.date.toLocaleDateString(
          "ar-SA"
        )
      : "—";

  return `
💵 آخر توزيع
💰 $${item.amount.toFixed(2)}
📅 ${dateText}
`.trim();
}

// ============================================================
// قائمة الأسهم
// ============================================================

async function getSymbols() {

  const now =
    Date.now();

  if (
    cachedSymbols.length > 0 &&
    now - symbolsCacheTime <
      15 * 60 * 1000
  ) {

    return cachedSymbols;
  }

  const lists = [

    "day_gainers",

    "most_actives",

    "growth_technology_stocks"
  ];

  const symbolMap =
    new Map();

  for (
    const list of lists
  ) {

    try {

      const url =
        `https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=${encodeURIComponent(list)}&count=250`;

      const data =
        await yahooFetch(
          url
        );

      const quotes =
        data?.finance?.result?.[0]?.quotes ||
        [];

      for (
        const item of quotes
      ) {

        const symbol =
          item?.symbol;

        if (
          !symbol ||
          !/^[A-Z0-9.\-]+$/.test(
            symbol
          )
        ) {

          continue;
        }

        if (
          symbol.includes("=") ||
          symbol.includes("^") ||
          symbol.includes("/")
        ) {

          continue;
        }

        // ================================================
        // استبعاد OTC
        // ================================================

        if (
          !isAllowedUSExchange(
            item
          )
        ) {

          continue;
        }

        const marketCap =
          Number(
            item?.marketCap
          );

        symbolMap.set(
          symbol,
          {

            symbol,

            marketCap:
              Number.isFinite(
                marketCap
              )
                ? marketCap
                : 0,

            exchange:
              item?.exchange ||
              "",

            fullExchangeName:
              item?.fullExchangeName ||
              "",

            shortName:
              item?.shortName ||
              ""
          }
        );

        if (
          symbolMap.size >=
          MAX_SYMBOLS
        ) {

          break;
        }
      }

    } catch (error) {

      console.log(
        `⚠️ تعذر تحميل ${list}:`,
        error.message
      );
    }

    if (
      symbolMap.size >=
      MAX_SYMBOLS
    ) {

      break;
    }
  }

  cachedSymbols =
    [...symbolMap.values()]
      .slice(
        0,
        MAX_SYMBOLS
      );

  symbolsCacheTime =
    now;

  console.log(
    `📋 تم تحميل ${cachedSymbols.length} سهم أمريكي`
  );

  return cachedSymbols;
}

// ============================================================
// جلب بيانات السهم
// ============================================================

async function getStockData(
  symbolInfo
) {

  const symbol =
    typeof symbolInfo === "string"
      ? symbolInfo
      : symbolInfo.symbol;

  const marketCap =
    typeof symbolInfo === "object"
      ? Number(
          symbolInfo.marketCap
        )
      : 0;

  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}` +
    `?range=5d&interval=5m&includePrePost=false`;

  const data =
    await yahooFetch(
      url
    );

  const result =
    data?.chart?.result?.[0];

  if (!result) {

    throw new Error(
      "لا توجد بيانات"
    );
  }

  const meta =
    result.meta || {};

  const quote =
    result.indicators?.quote?.[0];

  if (!quote) {

    throw new Error(
      "بيانات التداول غير موجودة"
    );
  }

  const closes =
    (quote.close || [])
      .map(Number)
      .filter(
        Number.isFinite
      );

  const highs =
    (quote.high || [])
      .map(Number)
      .filter(
        Number.isFinite
      );

  const lows =
    (quote.low || [])
      .map(Number)
      .filter(
        Number.isFinite
      );

  const volumes =
    (quote.volume || [])
      .map(Number)
      .filter(
        Number.isFinite
      );

  if (
    closes.length < 60
  ) {

    throw new Error(
      "بيانات غير كافية"
    );
  }

  const price =
    Number(
      meta.regularMarketPrice
    ) ||
    closes[
      closes.length - 1
    ];

  // ==========================================================
  // الحد الأدنى للسعر
  // ==========================================================

  if (
    !Number.isFinite(price) ||
    price < MIN_PRICE
  ) {

    throw new Error(
      `السعر أقل من $${MIN_PRICE}`
    );
  }

  const previousClose =
    Number(
      meta.previousClose
    ) ||
    Number(
      meta.chartPreviousClose
    ) ||
    closes[
      Math.max(
        0,
        closes.length - 2
      )
    ];

  if (
    !Number.isFinite(
      previousClose
    ) ||
    previousClose <= 0
  ) {

    throw new Error(
      "السعر السابق غير صالح"
    );
  }

  // ==========================================================
  // التغير
  // ==========================================================

  const change =
    (
      (price - previousClose) /
      previousClose
    ) * 100;

  // ==========================================================
  // EMA
  // ==========================================================

  const ema7 =
    calculateEMA(
      closes,
      7
    );

  const ema14 =
    calculateEMA(
      closes,
      14
    );

  const ema25 =
    calculateEMA(
      closes,
      25
    );

  const ema50 =
    calculateEMA(
      closes,
      50
    );

  const ema180 =
    calculateEMA(
      closes,
      180
    );

  // ==========================================================
  // VWAP
  // ==========================================================

  const vwap =
    calculateVWAP(
      highs,
      lows,
      closes,
      volumes
    );

  // ==========================================================
  // حجم التداول
  // ==========================================================

  const currentVolume =
    volumes.length
      ? volumes[
          volumes.length - 1
        ]
      : 0;

  const averageVolume =
    average(
      volumes.slice(
        Math.max(
          0,
          volumes.length - 50
        )
      )
    );

  let volumeStrength =
    0;

  if (
    averageVolume > 0
  ) {

    volumeStrength =
      clamp(
        (
          currentVolume /
          averageVolume
        ) * 50,
        0,
        100
      );
  }

  // ==========================================================
  // قوة VWAP
  // ==========================================================

  let vwapStrength =
    50;

  if (
    vwap > 0
  ) {

    const distance =
      (
        (price - vwap) /
        vwap
      ) * 100;

    vwapStrength =
      clamp(
        50 +
        distance * 20,
        0,
        100
      );
  }

  // ==========================================================
  // ضغط الشراء والبيع
  // ==========================================================

  let buyPressure =
    0;

  let sellPressure =
    0;

  const lookback =
    Math.min(
      24,
      closes.length - 1
    );

  for (
    let i =
      closes.length -
      lookback;

    i <
      closes.length;

    i++
  ) {

    const close =
      closes[i];

    const open =
      closes[i - 1];

    const volume =
      volumes[i] || 0;

    if (
      close > open
    ) {

      buyPressure +=
        volume;

    } else if (
      close < open
    ) {

      sellPressure +=
        volume;
    }
  }

  const totalPressure =
    buyPressure +
    sellPressure;

  let buyRatio =
    50;

  let sellRatio =
    50;

  if (
    totalPressure > 0
  ) {

    buyRatio =
      (
        buyPressure /
        totalPressure
      ) * 100;

    sellRatio =
      (
        sellPressure /
        totalPressure
      ) * 100;
  }

  // ==========================================================
  // السيولة
  // ==========================================================

  let liquidityState =
    "⚪ سيولة متوازنة";

  if (
    buyRatio >= 70 &&
    volumeStrength >= 60 &&
    price >= vwap
  ) {

    liquidityState =
      "🟢 دخول سيولة قوية";

  } else if (
    sellRatio >= 70 &&
    volumeStrength >= 60 &&
    price < vwap
  ) {

    liquidityState =
      "🔴 خروج سيولة";

  } else if (
    buyRatio >= 55
  ) {

    liquidityState =
      "🟢 دخول سيولة";

  } else if (
    sellRatio >= 55
  ) {

    liquidityState =
      "🔴 خروج سيولة";
  }

  // ==========================================================
  // التجميع / التصريف
  // ==========================================================

  let accumulation =
    "⚪ لا يوجد تجميع واضح";

  if (
    buyRatio >= 65 &&
    price >= vwap &&
    volumeStrength >= 55
  ) {

    accumulation =
      "🟢 تجميع قوي";

  } else if (
    buyRatio >= 55 &&
    price >= vwap
  ) {

    accumulation =
      "🟢 تجميع";

  } else if (
    sellRatio >= 65 &&
    price < vwap &&
    volumeStrength >= 55
  ) {

    accumulation =
      "🔴 تصريف قوي";

  } else if (
    sellRatio >= 55 &&
    price < vwap
  ) {

    accumulation =
      "🔴 تصريف";
  }

  // ==========================================================
  // حركة السهم
  // ==========================================================

  const movementLookback =
    Math.min(
      12,
      closes.length - 1
    );

  const movementStart =
    closes[
      closes.length -
      movementLookback -
      1
    ];

  let movementPercent =
    0;

  if (
    movementStart > 0
  ) {

    movementPercent =
      (
        (price -
          movementStart) /
        movementStart
      ) * 100;
  }

  let movementState =
    "⚪ حركة مستقرة";

  if (
    movementPercent >= 2
  ) {

    movementState =
      "🚀 حركة صاعدة قوية";

  } else if (
    movementPercent >= 0.5
  ) {

    movementState =
      "📈 حركة صاعدة";

  } else if (
    movementPercent <= -2
  ) {

    movementState =
      "🔻 حركة هابطة قوية";

  } else if (
    movementPercent <= -0.5
  ) {

    movementState =
      "📉 حركة هابطة";
  }

  // ==========================================================
  // قاع آخر 4 ساعات
  // 48 شمعة × 5 دقائق
  // ==========================================================

  const fourHourBars =
    Math.min(
      48,
      lows.length
    );

  const fourHourLow =
    Math.min(
      ...lows.slice(
        lows.length -
        fourHourBars
      )
    );

  const distanceFrom4HLow =
    fourHourLow > 0
      ? (
          (
            price -
            fourHourLow
          ) /
          fourHourLow
        ) * 100
      : 0;

  // ==========================================================
  // الاتجاه العام
  // ==========================================================

  let generalTrend =
    "⚪ الاتجاه العام متوازن";

  if (
    ema50 > ema180 &&
    price > ema50
  ) {

    generalTrend =
      "🟢 الاتجاه العام صاعد";

  } else if (
    ema50 < ema180 &&
    price < ema50
  ) {

    generalTrend =
      "🔴 الاتجاه العام هابط";
  }

  // ==========================================================
  // EMA
  // ==========================================================

  let emaSignal =
    "⚪ EMA متوازن";

  if (
    ema7 > ema14 &&
    ema14 > ema25 &&
    ema25 > ema50
  ) {

    emaSignal =
      "⚡ EMA سريع";

  } else if (
    ema7 < ema14 &&
    ema14 < ema25 &&
    ema25 < ema50
  ) {

    emaSignal =
      "🔻 EMA هابط";
  }

  // ==========================================================
  // الصعود اللحظي
  // ==========================================================

  let intradaySignal =
    "⚪ مستقر";

  if (
    price > ema7 &&
    ema7 > ema14 &&
    price > vwap
  ) {

    intradaySignal =
      "⚡ 📈 صعود لحظي";

  } else if (
    price < ema7 &&
    ema7 < ema14 &&
    price < vwap
  ) {

    intradaySignal =
      "⚡ 📉 هبوط لحظي";
  }

  // ==========================================================
  // قوة الانفجار
  // ==========================================================

  let explosionScore =
    0;

  if (
    change >= MIN_CHANGE
  ) {

    explosionScore +=
      15;
  }

  if (
    price > ema7
  ) {

    explosionScore +=
      10;
  }

  if (
    ema7 > ema14
  ) {

    explosionScore +=
      10;
  }

  if (
    ema14 > ema25
  ) {

    explosionScore +=
      10;
  }

  if (
    price > vwap
  ) {

    explosionScore +=
      10;
  }

  if (
    volumeStrength >= 60
  ) {

    explosionScore +=
      15;
  }

  if (
    buyRatio >= 65
  ) {

    explosionScore +=
      15;
  }

  if (
    generalTrend ===
    "🟢 الاتجاه العام صاعد"
  ) {

    explosionScore +=
      10;
  }

  // ==========================================================
  // الإشارة الرئيسية
  // ==========================================================

  let signal =
    "📊 ⚪ صعود غير مؤكد";

  const strongLiquidity =
    liquidityState ===
    "🟢 دخول سيولة قوية";

  const strongTrend =
    generalTrend ===
    "🟢 الاتجاه العام صاعد";

  const strongIntraday =
    intradaySignal ===
    "⚡ 📈 صعود لحظي";

  // ==========================================================
  // انفجار حقيقي
  // ==========================================================

  if (
    explosionScore >= 85 &&
    strongLiquidity &&
    strongTrend &&
    strongIntraday &&
    volumeStrength >= 60 &&
    price > vwap
  ) {

    signal =
      "📊 💀🚀 انفجار مؤكد";

  } else if (
    change >= MIN_CHANGE &&
    strongIntraday &&
    price > vwap &&
    volumeStrength >= 50 &&
    buyRatio >= 55
  ) {

    signal =
      "📊 🔥 صعود مؤكد";

  } else if (
    strongIntraday &&
    price > vwap
  ) {

    signal =
      "📊 🟡 صعود غير مؤكد";

  } else if (
    change <= -MIN_CHANGE &&
    price < ema7 &&
    ema7 < ema14 &&
    price < vwap &&
    volumeStrength >= 50
  ) {

    signal =
      "📊 🔻 هبوط";
  }

  // ==========================================================
  // Reverse Split
  // ==========================================================

  const reverseSplit =
    await getReverseSplitInfo(
      symbol
    );

  // ==========================================================
  // Dividend
  // ==========================================================

  const dividend =
    await getDividendInfo(
      symbol
    );

  // ==========================================================
  // النتيجة
  // ==========================================================

  return {

    symbol,

    marketCap,

    exchange:
      symbolInfo?.exchange ||
      "",

    fullExchangeName:
      symbolInfo?.fullExchangeName ||
      "",

    price,

    previousClose,

    change,

    ema7,

    ema14,

    ema25,

    ema50,

    ema180,

    vwap,

    currentVolume,

    averageVolume,

    volumeStrength,

    vwapStrength,

    buyRatio,

    sellRatio,

    liquidityState,

    accumulation,

    movementPercent,

    movementState,

    fourHourLow,

    distanceFrom4HLow,

    generalTrend,

    emaSignal,

    intradaySignal,

    explosionScore,

    signal,

    reverseSplit,

    dividend
  };
}

// ============================================================
// EMA
// ============================================================

function calculateEMA(
  values,
  period
) {

  if (
    !values.length
  ) {

    return 0;
  }

  const multiplier =
    2 /
    (period + 1);

  let ema =
    values[0];

  for (
    let i = 1;
    i < values.length;
    i++
  ) {

    ema =
      (
        values[i] -
        ema
      ) *
      multiplier +
      ema;
  }

  return ema;
}

// ============================================================
// VWAP
// ============================================================

function calculateVWAP(
  highs,
  lows,
  closes,
  volumes
) {

  let totalPV =
    0;

  let totalVolume =
    0;

  const length =
    Math.min(
      highs.length,
      lows.length,
      closes.length,
      volumes.length
    );

  const start =
    Math.max(
      0,
      length - 78
    );

  for (
    let i = start;
    i < length;
    i++
  ) {

    const high =
      highs[i];

    const low =
      lows[i];

    const close =
      closes[i];

    const volume =
      volumes[i];

    if (
      !Number.isFinite(high) ||
      !Number.isFinite(low) ||
      !Number.isFinite(close) ||
      !Number.isFinite(volume) ||
      volume <= 0
    ) {

      continue;
    }

    const typical =
      (
        high +
        low +
        close
      ) / 3;

    totalPV +=
      typical *
      volume;

    totalVolume +=
      volume;
  }

  if (
    totalVolume <= 0
  ) {

    return closes[
      closes.length - 1
    ];
  }

  return (
    totalPV /
    totalVolume
  );
}

// ============================================================
// Average
// ============================================================

function average(
  values
) {

  if (
    !values.length
  ) {

    return 0;
  }

  const sum =
    values.reduce(
      (
        a,
        b
      ) =>
        a + b,
      0
    );

  return (
    sum /
    values.length
  );
}

// ============================================================
// الأهداف
// ============================================================

function calculateTargets(
  entry
) {

  const percentages = [

    0.02,

    0.04,

    0.06,

    0.08,

    0.10,

    0.12,

    0.15,

    0.18
  ];

  return percentages.map(
    percent =>
      entry *
      (1 + percent)
  );
}

// ============================================================
// تنسيق الرسالة
// ============================================================

function formatSignal(
  data
) {

  const targets =
    calculateTargets(
      data.price
    );

  const targetText =
    targets
      .map(
        target =>
          `🎯 ${roundPrice(target)}`
      )
      .join("\n");

  const splitText =
    formatReverseSplit(
      data.reverseSplit
    );

  const dividendText =
    formatDividend(
      data.dividend
    );

  const movementSign =
    data.movementPercent >= 0
      ? "+"
      : "";

  return `
🇺🇸 السوق الأمريكي

${data.symbol}

💰 السعر:
$${roundPrice(data.price)}

🏦 القيمة السوقية:
${formatNumber(data.marketCap)}

📈 حركة السهم:
${data.movementState}
${movementSign}${data.movementPercent.toFixed(2)}%

📊 الاتجاه العام:
${data.generalTrend}

📦 قاع 4 ساعات:
$${roundPrice(data.fourHourLow)}

📐 فوق قاع 4س:
+${data.distanceFrom4HLow.toFixed(2)}%

${data.accumulation}

${data.signal}

📊 EMA:
${data.emaSignal}

${data.intradaySignal}

${data.liquidityState}

💪 قوة الفوليوم:
${data.volumeStrength.toFixed(0)}%

📦 حجم التداول:
${formatNumber(data.currentVolume)}

🔥 قوة VWAP:
${data.vwapStrength.toFixed(0)}%

🟢 ضغط شراء:
${data.buyRatio.toFixed(0)}%

🔴 ضغط بيع:
${data.sellRatio.toFixed(0)}%

💥 قوة الإشارة:
${data.explosionScore}/100

${dividendText
  ? `${dividendText}\n`
  : ""}

${splitText
  ? `${splitText}\n`
  : ""}

🎯 الأهداف:

${targetText}

━━━━━━━━━━━━
`.trim();
}

// ============================================================
// حفظ Chat ID
// ============================================================

function attachChatId(
  symbol,
  chatId
) {

  const item =
    sentSignals.get(
      symbol
    );

  if (!item) {

    return;
  }

  if (
    !item.chatIds
  ) {

    item.chatIds =
      [];
  }

  if (
    !item.chatIds.includes(
      chatId
    )
  ) {

    item.chatIds.push(
      chatId
    );
  }
}

// ============================================================
// إرسال الإشارة
// ============================================================

async function sendSignal(
  chatId,
  data
) {

  const old =
    sentSignals.get(
      data.symbol
    );

  const sameSignal =
    old &&
    old.signal ===
      data.signal &&
    old.liquidityState ===
      data.liquidityState &&
    old.accumulation ===
      data.accumulation &&
    old.generalTrend ===
      data.generalTrend &&
    Boolean(
      old.hasReverseSplit
    ) ===
      Boolean(
        data.reverseSplit?.found
      );

  if (
    sameSignal
  ) {

    attachChatId(
      data.symbol,
      chatId
    );

    return false;
  }

  const existing =
    old || {};

  sentSignals.set(
    data.symbol,
    {

      ...data,

      entryPrice:
        existing.entryPrice ||
        data.price,

      targetsHit:
        existing.targetsHit ||
        [],

      chatIds:
        existing.chatIds ||
        [],

      hasReverseSplit:
        Boolean(
          data.reverseSplit?.found
        )
    }
  );

  attachChatId(
    data.symbol,
    chatId
  );

  await bot.sendMessage(
    chatId,
    formatSignal(
      data
    )
  );

  return true;
}

// ============================================================
// الفحص
// ============================================================

async function scan(
  chatId
) {

  if (
    scanning
  ) {

    return;
  }

  scanning =
    true;

  console.log(
    "🔎 بدء فحص السوق..."
  );

  try {

    const symbols =
      await getSymbols();

    let found =
      0;

    for (
      const symbolInfo of
        symbols
    ) {

      try {

        const data =
          await getStockData(
            symbolInfo
          );

        // ====================================================
        // فقط $0.10 فأعلى
        // ====================================================

        if (
          data.price <
          MIN_PRICE
        ) {

          continue;
        }

        // ====================================================
        // 🚀 الانفجار المؤكد
        // ====================================================

        if (
          data.signal ===
          "📊 💀🚀 انفجار مؤكد"
        ) {

          const sent =
            await sendSignal(
              chatId,
              data
            );

          if (
            sent
          ) {

            found++;
          }

        // ====================================================
        // صعود مؤكد
        // ====================================================

        } else if (
          data.signal ===
          "📊 🔥 صعود مؤكد"
        ) {

          const sent =
            await sendSignal(
              chatId,
              data
            );

          if (
            sent
          ) {

            found++;
          }

        // ====================================================
        // Reverse Split اليوم
        // ====================================================

        } else if (
          data.reverseSplit?.found &&
          data.reverseSplit?.period ===
            "🔴 اليوم"
        ) {

          const sent =
            await sendSignal(
              chatId,
              data
            );

          if (
            sent
          ) {

            found++;
          }
        }

      } catch (error) {

        console.log(
          `⚠️ ${symbolInfo.symbol}:`,
          error.message
        );
      }

      await sleep(
        REQUEST_DELAY_MS
      );
    }

    lastScanCount =
      found;

    lastScanTime =
      new Date();

    console.log(
      `✅ انتهى الفحص — ${found} إشارة جديدة`
    );

  } finally {

    scanning =
      false;
  }
}

// ============================================================
// تحديث الإشارات
// ============================================================

async function updateSignals() {

  if (
    sentSignals.size === 0
  ) {

    return;
  }

  for (
    const [
      symbol,
      old
    ] of
      sentSignals
  ) {

    try {

      const symbolInfo = {

        symbol,

        marketCap:
          old.marketCap || 0,

        exchange:
          old.exchange || "",

        fullExchangeName:
          old.fullExchangeName || ""
      };

      const data =
        await getStockData(
          symbolInfo
        );

      // ======================================================
      // تحديث البيانات
      // ======================================================

      old.price =
        data.price;

      old.change =
        data.change;

      old.marketCap =
        data.marketCap;

      old.volumeStrength =
        data.volumeStrength;

      old.currentVolume =
        data.currentVolume;

      old.vwapStrength =
        data.vwapStrength;

      old.buyRatio =
        data.buyRatio;

      old.sellRatio =
        data.sellRatio;

      old.liquidityState =
        data.liquidityState;

      old.accumulation =
        data.accumulation;

      old.movementPercent =
        data.movementPercent;

      old.movementState =
        data.movementState;

      old.fourHourLow =
        data.fourHourLow;

      old.distanceFrom4HLow =
        data.distanceFrom4HLow;

      old.generalTrend =
        data.generalTrend;

      old.emaSignal =
        data.emaSignal;

      old.intradaySignal =
        data.intradaySignal;

      old.explosionScore =
        data.explosionScore;

      old.signal =
        data.signal;

      old.reverseSplit =
        data.reverseSplit;

      old.dividend =
        data.dividend;

      // ======================================================
      // Reverse Split جديد
      // ======================================================

      const currentlyHasSplit =
        Boolean(
          data.reverseSplit?.found
        );

      if (
        currentlyHasSplit &&
        !old.hasReverseSplit
      ) {

        old.hasReverseSplit =
          true;

        for (
          const chatId of
            old.chatIds || []
        ) {

          await bot.sendMessage(
            chatId,
            `
🚨 🔄 تقسيم عكسي جديد

🇺🇸 السوق الأمريكي

${symbol}

💰 السعر:
$${roundPrice(
  data.price
)}

${formatReverseSplit(
  data.reverseSplit
)}

📊 الاتجاه:
${data.generalTrend}

${data.accumulation}

${data.liquidityState}

💥 قوة الإشارة:
${data.explosionScore}/100

━━━━━━━━━━━━
`.trim()
          );
        }

      } else if (
        !currentlyHasSplit
      ) {

        old.hasReverseSplit =
          false;
      }

      // ======================================================
      // مراقبة الأهداف
      // ======================================================

      const targets =
        calculateTargets(
          old.entryPrice
        );

      for (
        let i = 0;
        i < targets.length;
        i++
      ) {

        const target =
          targets[i];

        if (
          data.price >=
            target &&
          !old.targetsHit.includes(
            i
          )
        ) {

          old.targetsHit.push(
            i
          );

          console.log(
            `🎯 ${symbol} وصل الهدف ${i + 1}`
          );

          for (
            const chatId of
              old.chatIds || []
          ) {

            await bot.sendMessage(
              chatId,
              `
🎯 تحقق الهدف ${i + 1}

🇺🇸 ${symbol}

💰 السعر:
$${roundPrice(
  data.price
)}

🎯 الهدف:
$${roundPrice(
  target
)}

📊 الاتجاه:
${data.generalTrend}

${data.accumulation}

${data.liquidityState}

💪 الفوليوم:
${data.volumeStrength.toFixed(0)}%

━━━━━━━━━━━━
`.trim()
            );
          }
        }
      }

    } catch (error) {

      console.log(
        `⚠️ تحديث ${symbol}:`,
        error.message
      );
    }

    await sleep(
      REQUEST_DELAY_MS
    );
  }
}

// ============================================================
// /start
// ============================================================

bot.onText(
  /\/start/,
  async msg => {

    const chatId =
      msg.chat.id;

    await bot.sendMessage(
      chatId,
      `
🇺🇸 بوت الأسهم الأمريكية PRO MAX

💵 الحد الأدنى:
$${MIN_PRICE.toFixed(2)}

🇺🇸 NYSE / NASDAQ / AMEX
🚫 OTC مستبعد

📊 رصد حركة السهم
🟢 التجميع
🔴 التصريف
💰 القيمة السوقية
📉 قاع 4 ساعات
📊 الاتجاه العام
⚡ EMA
🔥 VWAP
💪 السيولة
📦 الفوليوم
💵 التوزيعات
🔄 Reverse Split

🚀 انفجار مؤكد
فقط عند اكتمال عدة شروط.

🎯 8 أهداف

الأوامر:

/scan
/signals
/status
/refresh
/stop

━━━━━━━━━━━━
`.trim()
    );
  }
);

// ============================================================
// /scan
// ============================================================

bot.onText(
  /\/scan/,
  async msg => {

    const chatId =
      msg.chat.id;

    await bot.sendMessage(
      chatId,
      "🔎 بدأ فحص السوق الأمريكي..."
    );

    await scan(
      chatId
    );

    for (
      const [
        symbol
      ] of sentSignals
    ) {

      attachChatId(
        symbol,
        chatId
      );
    }

    await bot.sendMessage(
      chatId,
      `
✅ انتهى الفحص

📊 إشارات جديدة:
${lastScanCount}

🇺🇸 NYSE / NASDAQ / AMEX

💵 الحد الأدنى:
$${MIN_PRICE.toFixed(2)}

⏱ آخر فحص:
${
  lastScanTime
    ? lastScanTime.toLocaleString(
        "ar-SA"
      )
    : "—"
}
`.trim()
    );
  }
);

// ============================================================
// /signals
// ============================================================

bot.onText(
  /\/signals/,
  async msg => {

    const chatId =
      msg.chat.id;

    if (
      sentSignals.size === 0
    ) {

      await bot.sendMessage(
        chatId,
        "📭 لا توجد إشارات حالياً."
      );

      return;
    }

    let text =
      "📊 مراقبة الأسهم الحالية\n\n";

    let count =
      0;

    for (
      const [
        symbol,
        data
      ] of sentSignals
    ) {

      text +=
        `🇺🇸 ${symbol}\n`;

      text +=
        `💰 $${roundPrice(
          data.price
        )}\n`;

      text +=
        `${data.signal}\n`;

      text +=
        `${data.generalTrend}\n`;

      text +=
        `${data.accumulation}\n`;

      text +=
        `📉 قاع 4س: $${roundPrice(
          data.fourHourLow
        )}\n`;

      text +=
        `💥 ${data.explosionScore}/100\n`;

      if (
        data.reverseSplit?.found
      ) {

        text +=
          `🔄 ${data.reverseSplit.period} — ${data.reverseSplit.ratio}\n`;
      }

      text +=
        "\n";

      count++;

      if (
        count >= 30
      ) {

        break;
      }
    }

    await bot.sendMessage(
      chatId,
      text.trim()
    );
  }
);

// ============================================================
// /status
// ============================================================

bot.onText(
  /\/status/,
  async msg => {

    const chatId =
      msg.chat.id;

    await bot.sendMessage(
      chatId,
      `
🟢 حالة البوت

📡 Telegram:
يعمل

📊 الإشارات:
${sentSignals.size}

📋 الأسهم:
${cachedSymbols.length}

🇺🇸 الأسواق:
NYSE / NASDAQ / AMEX

🚫 OTC:
مستبعد

💵 الحد الأدنى:
$${MIN_PRICE.toFixed(2)}

🔎 الفحص:
${scanning
  ? "جارٍ"
  : "متوقف"}

⏱ آخر فحص:
${
  lastScanTime
    ? lastScanTime.toLocaleString(
        "ar-SA"
      )
    : "لم يبدأ"
}

━━━━━━━━━━━━
`.trim()
    );
  }
);

// ============================================================
// /refresh
// ============================================================

bot.onText(
  /\/refresh/,
  async msg => {

    const chatId =
      msg.chat.id;

    cachedSymbols =
      [];

    symbolsCacheTime =
      0;

    splitCache.clear();

    dividendCache.clear();

    await bot.sendMessage(
      chatId,
      "🔄 تم تحديث الأسهم + Reverse Split + التوزيعات."
    );
  }
);

// ============================================================
// /stop
// ============================================================

bot.onText(
  /\/stop/,
  async msg => {

    const chatId =
      msg.chat.id;

    sentSignals.clear();

    await bot.sendMessage(
      chatId,
      "🛑 تم مسح الإشارات الحالية."
    );
  }
);

// ============================================================
// تحديث كل 30 ثانية
// ============================================================

setInterval(
  async () => {

    try {

      await updateSignals();

    } catch (error) {

      console.log(
        "⚠️ خطأ في التحديث:",
        error.message
      );
    }

  },
  UPDATE_INTERVAL_SEC * 1000
);

// ============================================================
// الفحص التلقائي
// ============================================================

setInterval(
  async () => {

    console.log(
      "⏰ الفحص التلقائي..."
    );

    const chats =
      new Set();

    for (
      const data of
        sentSignals.values()
    ) {

      for (
        const chatId of
          data.chatIds || []
      ) {

        chats.add(
          chatId
        );
      }
    }

    for (
      const chatId of chats
    ) {

      try {

        await scan(
          chatId
        );

      } catch (error) {

        console.log(
          "⚠️ خطأ في الفحص:",
          error.message
        );
      }
    }

  },
  SCAN_INTERVAL_MIN *
  60 *
  1000
);

// ============================================================
// Express
// ============================================================

app.get(
  "/",
  (req, res) => {

    res.send(
      "🇺🇸 US Stock Telegram Bot PRO MAX — Running"
    );
  }
);

app.get(
  "/health",
  (req, res) => {

    res.json({

      status:
        "ok",

      signals:
        sentSignals.size,

      scanning,

      lastScanTime,

      minPrice:
        MIN_PRICE,

      exchanges:
        [
          "NASDAQ",
          "NYSE",
          "AMEX"
        ],

      otc:
        false
    });
  }
);

// ============================================================
// تشغيل السيرفر
// ============================================================

app.listen(
  PORT,
  () => {

    console.log(
      `🚀 Server running on port ${PORT}`
    );

    console.log(
      "🤖 Telegram bot is running"
    );

    console.log(
      "🇺🇸 NYSE / NASDAQ / AMEX ONLY"
    );

    console.log(
      "🚫 OTC excluded"
    );

    console.log(
      `💵 Minimum price: $${MIN_PRICE.toFixed(2)}`
    );

    console.log(
      "📊 Movement monitoring enabled"
    );

    console.log(
      "🟢 Accumulation / 🔴 Distribution enabled"
    );

    console.log(
      "💰 Market Cap enabled"
    );

    console.log(
      "📉 4H Low enabled"
    );

    console.log(
      "📊 General Trend enabled"
    );

    console.log(
      "🔄 Reverse Split detection enabled"
    );

    console.log(
      "💵 Dividend detection enabled"
    );

    console.log(
      "🚀 Strong Explosion Filter enabled"
    );
  }
);