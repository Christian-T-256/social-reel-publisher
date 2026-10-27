# Live API setup

The demo and tests do not need this setup. These steps are only for posting to real accounts.

## 1. Create an isolated secrets directory

Use a different directory for every brand or account set. The directory is ignored by Git when it is inside this repository.

```bash
cp .env.example .env
export SOCIAL_PUBLISHER_SECRETS_DIR="$PWD/.local-secrets/example-brand"
mkdir -p "$SOCIAL_PUBLISHER_SECRETS_DIR"
chmod 700 "$SOCIAL_PUBLISHER_SECRETS_DIR"
cp config.example.json config.json
```

Do not put access tokens, client secrets, or the generated `destination_pins.json` in version control.

## 2. YouTube OAuth

In Google Cloud, enable YouTube Data API v3 and create an OAuth desktop client. Download its client JSON into the secrets directory, then run:

```bash
export YOUTUBE_CLIENT_SECRETS_FILE="$SOCIAL_PUBLISHER_SECRETS_DIR/youtube-client.json"
python3 scripts/youtube_oauth.py
python3 -m reel_publisher --config config.json --pin youtube
```

The helper requests both upload and read-only scopes. The read-only scope is required to resolve the channel selected by the credential. The account chooser is forced during consent so a previously selected personal channel is not silently reused.

## 3. Instagram OAuth

Create an app with Instagram API access, configure Instagram Login, and request a token with the permissions needed to publish content and read the current profile. The helper accepts the token through hidden terminal input, validates it, and writes it with mode `0600`:

```bash
python3 scripts/instagram_oauth.py
python3 -m reel_publisher --config config.json --pin instagram
```

Instagram fetches the video from `--url`. The URL must be public and return a supported vertical MP4.
Refresh a long-lived token before it expires with `python3 scripts/instagram_oauth.py --refresh`.

## 4. TikTok OAuth

Create a TikTok developer app with Login Kit and the Content Posting API. Add `user.info.basic` and `video.upload`, register `http://localhost:8765/` as a desktop redirect URI, and verify the domain that hosts the video URL.

```bash
export TIKTOK_CLIENT_KEY=your_client_key
export TIKTOK_CLIENT_SECRET=your_client_secret
export TIKTOK_REDIRECT_PORT=8765
python3 scripts/tiktok_oauth.py
python3 -m reel_publisher --config config.json --pin tiktok
```

The TikTok flow sends the video to the creator inbox as a draft. Add audio and complete the public post in the TikTok app.

## 5. Verify all pins

Run a read-only destination audit before a campaign or scheduled publishing session:

```bash
python3 -m reel_publisher --config config.json --verify
```

If any account is missing, unreadable, or different from its pin, the command exits nonzero. Reauthorize the intended account first. Only use `--pin PLATFORM` when you intentionally want to replace the allowed destination.

## 6. Review, then publish

First omit `--confirm` and inspect the plan. Add `--confirm` only after the title, caption, media, and destinations are correct.

```bash
python3 -m reel_publisher \
  --config config.json \
  --file media/final-reel.mp4 \
  --url https://media.example.com/final-reel.mp4 \
  --title "A clearer patient check-in" \
  --caption "Three small changes that reduce front desk friction. #Operations" \
  --results-json results.json \
  --confirm
```

The result ledger contains artifact IDs, terminal states, and verified destination IDs. It contains no tokens.
