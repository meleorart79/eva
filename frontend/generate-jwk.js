const fs = require("fs");
const { createPublicKey } = require("crypto");
const { exportJWK } = require("jose");

(async () => {
    const pem = fs.readFileSync("private.key", "utf8");

    const key = createPublicKey(pem);

    const jwk = await exportJWK(key);

    jwk.use = "sig";
    jwk.kid = "revolut-sandbox-key-1";

    console.log(JSON.stringify({ keys: [jwk] }, null, 2));
})();