Below is a **full production-ready Python Telegram bot**, with:

* **User management in SQLite**
* **OpenRouter LLM integration** (generates and assigns motivational messages in bulk)
* **Hardness feedback and per-user adaptation**
* **Every-8-hour scheduling for 365 days**
* **Clean async code, error handling, batching, logging**

---

## **Stop Smoking Coach — Full Code**

**File structure recommended:**

```
.
├── bot.py
├── openrouter_llm.py
├── users.db
├── requirements.txt
```

### **requirements.txt**

```
python-telegram-bot==20.0b0
apscheduler
openai
aiosqlite
```

Install with:

```bash
pip install -r requirements.txt
```

---

## **How it works**

* On `/start`, user is registered in SQLite.
* LLM generates a batch of motivational messages per user (light/medium/hard), each scheduled for delivery.
* Every 8 hours, user gets their next message for 365 days.
* User feedback with buttons adapts their “hardness” for future messages.
* All messages, user states, and schedules are stored in DB.
* Robust async code with error handling and logging.

---

## **To Run**

1. **Set API keys** in your environment:

   ```
   export TELEGRAM_TOKEN=your_telegram_token
   export OPENROUTER_API_KEY=your_openrouter_api_key
   ```
2. **Install dependencies**:

   ```
   pip install -r requirements.txt
   ```
3. **Run the bot**:

   ```
   python bot.py
   ```

---

## **Tips & Enhancements**

* If you want to **generate messages in larger batches** (for all users at once), just adjust `generate_motivations_bulk` to use a higher count, and randomize assignment per user.
* You can easily scale this with Postgres or any other database.
* Add `/stop` to allow users to pause or leave.
* To reduce API cost, **reuse previously generated messages** among users for the same day/hardness.

---

Here’s a production-ready **Dockerfile** and **docker-compose.yml** for Stop Smoking Coach bot.

---

## **1. Dockerfile**

This setup uses a **slim Python image**, installs your dependencies, and sets up your bot for production use.

```dockerfile
# ---- Dockerfile ----
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# System deps (optional but useful for pip, SSL, etc.)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy all source code
COPY . .

# Set environment variables for Python (UTF-8, no .pyc)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Entrypoint: run your bot
CMD ["python", "bot.py"]
```

---

## **2. docker-compose.yml**

Set up your bot service with required environment variables.
Replace the `TELEGRAM_TOKEN` and `OPENROUTER_API_KEY` with your real keys or use Docker secrets for better security.

```yaml
version: '3.8'

services:
  bot:
    build: .
    container_name: stop-smoking-coach
    restart: unless-stopped
    environment:
      TELEGRAM_TOKEN: "YOUR_TELEGRAM_BOT_TOKEN"
      OPENROUTER_API_KEY: "YOUR_OPENROUTER_API_KEY"
      # (optional) Set your site if you want for LLM ranking:
      # REFERER: "https://yourdomain.com"
      # TITLE: "StopSmokingCoach"
    volumes:
      - ./users.db:/app/users.db  # Persist the sqlite DB
    # If you need logs outside the container:
    #   - ./logs:/app/logs
```

---

## **3. Usage:**

* Place your `Dockerfile`, `docker-compose.yml`, `requirements.txt`, and all your `.py` files in the **same directory**.
* Build and start the bot:

```bash
docker compose up --build -d
```

* Check logs:

```bash
docker compose logs -f
```

---

## **Security notes:**

* For production, use Docker **secrets** for your keys or pass them at runtime, not in plain YAML.
* The database is persisted on your host via `volumes`, so bot restarts don't lose user data.

---

**Ready!**
If you want to add more config, like logging, or want an example with Docker secrets—just say the word!

