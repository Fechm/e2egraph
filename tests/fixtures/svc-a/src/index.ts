const base = process.env.USERS_API_URL;
const key = process.env.ACME_SECRET_KEY;
await fetch(`${base}/v1/users`);
