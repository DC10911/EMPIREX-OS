const p = require("@babel/parser");
const fs = require("fs");
try {
    const s = fs.readFileSync("home-live.html", "utf8");
    const m = s.match(/<script type="text\/babel">([\s\S]*?)<\/script>/);
    if (!m) {
        console.log("ERR script tag not found");
        process.exit(1);
    }
    const js = m[1];
    p.parse(js, { sourceType: "module", plugins: ["jsx"] });
    console.log("OK");
} catch (e) {
    console.log("ERR", e.message);
    if (e.loc) {
        console.log("line", e.loc.line, "col", e.loc.column);
        const s = fs.readFileSync("home-live.html", "utf8");
        const m = s.match(/<script type="text\/babel">([\s\S]*?)<\/script>/);
        const js = m[1];
        const lines = js.split("\n");
        console.log("CTX:", lines.slice(Math.max(0, e.loc.line - 3), e.loc.line + 2).join("\n"));
    }
}
