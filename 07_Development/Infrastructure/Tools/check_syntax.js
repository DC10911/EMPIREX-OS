try {
  const p = require("@babel/parser");
  const fs = require("fs");
  const s = fs.readFileSync("home-live.html", "utf8");
  const m = s.match(/<script type="text\/babel">([\s\S]*?)<\/script>/);
  if (!m) {
    console.log("ERR script tag not found");
    process.exit(0);
  }
  const js = m[1];
  p.parse(js, { sourceType: "module", plugins: ["jsx"] });
  console.log("OK");
} catch (e) {
  if (e.code === 'MODULE_NOT_FOUND' && e.message.includes('@babel/parser')) {
    console.log('no babel parser');
  } else {
    console.log("ERR", e.message, "at line", e.loc && e.loc.line);
  }
}
