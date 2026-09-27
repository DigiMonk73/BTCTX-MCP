// Login rules the server enforces (backend/schemas/user.py,
// backend/services/first_run.py), said the same way on every form.

export const MIN_PASSWORD_LENGTH = 12;
export const PASSWORD_RULE = `At least ${MIN_PASSWORD_LENGTH} characters.`;

export const SETUP_CODE_HINT =
  "It is printed in the server's log at startup (docker logs <container>) " +
  "and saved as setup-code.txt in the data folder (/data on Docker).";
