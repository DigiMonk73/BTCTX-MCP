// Login rules the server enforces (backend/schemas/user.py,
// backend/services/first_run.py), said the same way on every form.

export const MIN_PASSWORD_LENGTH = 12;
export const PASSWORD_RULE = `At least ${MIN_PASSWORD_LENGTH} characters.`;

export const SETUP_CODE_HINT =
  "It is printed in the server's log at startup (docker logs <container>) " +
  "and saved as setup-code.txt in the data folder (/data on Docker).";

// The Mac app's window, when it can't fill the code in itself
export const MAC_SETUP_CODE_HINT =
  "It is saved as setup-code.txt in BitcoinTX's data folder (~/Library/Application Support/BitcoinTX). " +
  "Once logged in, set your own username and password in Settings.";
