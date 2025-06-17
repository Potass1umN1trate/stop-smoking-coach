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

If you need deployment tips (Docker, Heroku, etc), more features, or want to tweak the logic, just ask!
