# EMPIREX OS Render Deployment

This service is ready for Render, but production login codes will only be delivered after you configure a real provider.

## Required secrets

Set these in the Render dashboard before the first production deploy:

- `OTP_SECRET`: at least 32 random characters
- `APP_BASE_URL`: your final HTTPS domain, for example `https://app.empirexos.com`
- `SMTP_HOST`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`

Optional for SMS delivery:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`

## Data persistence

`render.yaml` mounts a persistent disk at `/var/data` and points `EMPIREX_DB_PATH` to `/var/data/empirex_leads.db` so registrations, sessions, journal data, and agent tables survive restarts and deploys.

## Deploy steps

1. Initialize git in this folder.
2. Add the files and push to GitHub.
3. Create a new Render Blueprint or Web Service from the repository.
4. Confirm the environment variables above.
5. Deploy and wait for `/api/health` to return `ok: true`.
6. Test registration with a real email before opening access publicly.

## First login test

- Email channel works only when SMTP is configured.
- Phone channel works only when Twilio is configured.
- In development, the server prints the OTP to logs instead of sending it.

Without SMTP or Twilio, production registration will fail by design.