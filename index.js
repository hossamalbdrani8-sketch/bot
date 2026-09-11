
const http = require('http');

// --- كود الفحص التشخيصي ---
const server = http.createServer((req, res) => {
  if (req.url === '/debug/env') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    // فحص المتغيرات التي تبدأ بالأسماء المتوقعة
    const keys = Object.keys(process.env).filter(key => 
      key.startsWith('RAILWAY_') || 
      key.startsWith('EODHD') || 
      key.startsWith('CRYPTO') || 
      key.startsWith('TASI') || 
      key.startsWith('US_CONF')
    );
    
    res.end(JSON.stringify({
      count: Object.keys(process.env).length,
      has_eodhd_token: !!process.env.EODHD_API_TOKEN, // تأكد أن هذا الاسم يطابق الموجود في Railway
      has_crypto_key: !!process.env.CRYPTO_API_KEY,   // تأكد أن هذا الاسم يطابق الموجود في Railway
      keys: keys.sort()
    }, null, 2));
  } else {
    res.writeHead(404);
    res.end();
  }
});

const port = process.env.PORT || 8080;
server.listen(port, () => {
  console.log(`✅ خادم الفحص يعمل على المنفذ ${port}`);
});
// --- نهاية كود الفحص التشخيصي ---


// ... هنا باقي كود البوت الخاص بك (لا تحذف أي شيء منه) ...