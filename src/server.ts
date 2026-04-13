import dotenv from "dotenv";

import app from "./app";

dotenv.config();

const port = Number(process.env.PORT) || 3000;

app.listen(port, () => {
  // Keep startup output concise and visible in local/dev logs.
  // eslint-disable-next-line no-console
  console.log(`Server listening on port ${port}`);
});
